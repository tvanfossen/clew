# SPDX-License-Identifier: MIT
"""The acceptance CLI: plan, generate, grade, report — as four separate commands.

SEPARATE ON PURPOSE. `generate` freezes answers and `grade` reads them, and nothing runs both in
one process. Two reasons, both learned the expensive way:

  * the judge has to be arm-blind, and grading inline puts the grader in the same process as the
    thing that knows the arm;
  * grading is cheap and re-runnable, so coupling it to generation means a scorer fix costs a
    regeneration — which is how a previous set of grids ended up spanning two scorer versions
    with nothing able to reconcile them.

`plan` prints what a run WOULD do and spends nothing. Run it before generate; a run whose
execution order was never looked at is one whose ordering defects are found afterwards, in the
numbers.

Usage:
    .venv/bin/python -m acceptance plan     --rubric <path> --models sonnet [--replicates 1]
    .venv/bin/python -m acceptance generate --rubric <path> --repo <tree> --out <dir> \\
                                            --models sonnet [--mcp-config <path>]
    .venv/bin/python -m acceptance grade    --rubric <path> --answers <dir>
    .venv/bin/python -m acceptance report   --answers <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .execute import index_cells_that_never_used_the_index, run_cell
from .grader.rubric import RubricError, load
from .grader.score import score_question
from .runner import check_revision, check_symmetry, plan, rubric_digest


## @brief Load a rubric, refusing loudly rather than half-parsing.
## @param path Rubric path.
## @return Rubric, or None after printing the refusal.
## @version 1
def _rubric(path: Path):
    """@brief Load a rubric for the CLI.
    @return Rubric or None.
    @version 1
    """
    try:
        return load(path)
    except RubricError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return None


## @brief Print the ordered cell plan without running anything.
## @param args Parsed arguments.
## @return Exit code.
## @version 1
def cmd_plan(args) -> int:
    """@brief Show what a run would do.
    @return Exit code.
    @version 1
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    check_symmetry()
    cells = plan(rubric, tuple(args.models), args.replicates, args.seed)
    print(f"{rubric.target} @ {rubric.commit[:10]}  rubric {rubric.version}")
    print(f"digest {rubric_digest(args.rubric)}  seed {args.seed}  {len(cells)} cells")
    for cell in cells:
        print(f"  {cell.order:>4}  {cell.stem()}")
    return 0


## @brief Run every cell and freeze its artifacts.
## @param args Parsed arguments.
## @return Exit code.
## @version 1
def cmd_generate(args) -> int:
    """PREFLIGHT BEFORE THE FIRST CELL, not per cell. A revision mismatch found on cell 40 has
    already spent 39 cells against the wrong tree.

    @brief Generate answers.
    @return Exit code.
    @version 1
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    try:
        check_symmetry()
        check_revision(rubric, args.repo)
    except ValueError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1

    prompts = {q.id: q.prompt for q in rubric.questions}
    cells = plan(rubric, tuple(args.models), args.replicates, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "run.json").write_text(
        json.dumps(
            {
                "target": rubric.target,
                "commit": rubric.commit,
                "rubric_version": rubric.version,
                "rubric_digest": rubric_digest(args.rubric),
                "seed": args.seed,
                "models": list(args.models),
                "replicates": args.replicates,
                "cells": [asdict(c) for c in cells],
            },
            indent=2,
        ),
        "utf-8",
    )

    failed = 0
    results = []
    for cell in cells:
        result = run_cell(
            cell, prompts[cell.question_id], args.repo, args.out, args.mcp_config, args.timeout
        )
        flag = "ok " if result.ok else "ERR"
        print(
            f"{flag} {cell.stem():<34} {result.seconds:6.1f}s "
            f"out {result.output_tokens:>7} cache {result.cache_read_tokens:>8} "
            f"{result.result_bytes:>7} B turns {result.turns:>3} "
            f"tools {result.tool_calls:>3}/{result.non_index_tool_calls:>3} "
            f"denied {result.denied_tool_calls:>2}" + (f"  {result.error}" if result.error else "")
        )
        results.append(result)
        failed += 0 if result.ok else 1
    ## THE FAILED COUNT IS PRINTED EVEN WHEN ZERO. A run that silently omits it cannot be told
    ## from one whose failures were never counted.
    print(f"\n{len(cells) - failed}/{len(cells)} cells produced an answer")
    blind = index_cells_that_never_used_the_index(results)
    if blind:
        print(
            f"\nWARNING — {len(blind)} index cell(s) made ZERO index calls: {blind}\n"
            f"That is what an index arm running WITHOUT its index looks like: the server starts, "
            f"finds no database, registers no query tools, and the agent answers from the source "
            f"with no error anywhere. Verify the MCP config resolves before trusting these cells."
        )
    return 1 if failed else 0


## @brief Grade every frozen answer against the rubric.
## @param args Parsed arguments.
## @return Exit code.
## @version 1
def cmd_grade(args) -> int:
    """Reads only the frozen `.md` files. A cell that failed left none, so it cannot be graded
    as an answer that said nothing.

    @brief Grade answers.
    @return Exit code.
    @version 1
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    questions = {q.id: q for q in rubric.questions}
    graded = 0
    for path in sorted(args.answers.glob("*.md")):
        parts = path.stem.split("_")
        if len(parts) < 4 or parts[0] not in questions:
            continue
        qid, arm = parts[0], parts[2]
        result = score_question(questions[qid], path.read_text("utf-8"), rubric, arm)
        got, unmarked = result.score()
        (args.answers / f"{path.stem}.grade.json").write_text(
            json.dumps(
                {
                    "cell": path.stem,
                    "arm": arm,
                    "rubric_version": rubric.version,
                    "rubric_digest": rubric_digest(args.rubric),
                    "judge_model": rubric.judge_model,
                    "score": got,
                    "unmarked_pct": unmarked,
                    "decisions": [asdict(d) for d in result.decisions],
                },
                indent=2,
            ),
            "utf-8",
        )
        print(f"{path.stem:<34} score {got:6.1%}  unmarked {unmarked:5.1%}")
        graded += 1
    if not graded:
        print("no answers found — nothing was graded", file=sys.stderr)
        return 1
    return 0


## @brief Report the three axes per cell, from frozen artifacts only.
## @param args Parsed arguments.
## @return Exit code.
## @version 1
def cmd_report(args) -> int:
    """ALL THREE AXES, EVERY TIME, and cost as TWO numbers. `total_tokens` is a turn counter
    times a mostly-cached prompt, so it tracks round trips far more closely than anything
    retrieved — and the two have disagreed in SIGN on the same run. `unmarked_pct` sits beside
    every score, because a mark the judge never ruled on is not a miss.

    NO VERDICT IS PRINTED. The harness reports; the owner rules.

    @brief Report a run.
    @return Exit code.
    @version 1
    """
    rows = []
    for meta_path in sorted(args.answers.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text("utf-8"))
        grade_path = args.answers / f"{meta['stem']}.grade.json"
        grade = json.loads(grade_path.read_text("utf-8")) if grade_path.is_file() else {}
        rows.append((meta, grade))
    if not rows:
        print("no cells found", file=sys.stderr)
        return 1

    head = (
        f"{'cell':<34} {'time':>7} {'out tok':>8} {'cache tok':>10} {'bytes':>8} "
        f"{'turns':>6} {'tools':>6} {'!idx':>5} {'deny':>5} {'score':>7} {'unmkd':>6}"
    )
    print(head)
    print("-" * len(head))
    for meta, grade in rows:
        score = f"{grade['score']:6.1%}" if grade else "     —"
        unmarked = f"{grade['unmarked_pct']:5.1%}" if grade else "    —"
        print(
            f"{meta['stem']:<34} {meta['seconds']:6.1f}s {meta['output_tokens']:>8} "
            f"{meta['cache_read_tokens']:>10} {meta['result_bytes']:>8} {meta['turns']:>6} "
            f"{meta['tool_calls']:>6} {meta['non_index_tool_calls']:>5} "
            f"{meta['denied_tool_calls']:>5} {score:>7} {unmarked:>6}"
        )
    print("\nOUT TOK and CACHE TOK are reported apart, never summed. Measured on one cell:")
    print(
        "534,192 cached against 7,292 output — a blended figure describes the prefix, not the work."
    )
    print("!idx = tool calls that did not use the index, the lever under test.")
    print("-1 in a tool column means the count could not be determined, NOT zero.")
    print("DENY on the BASELINE arm is contamination: it reached for a tool it should not see.")
    return 0


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """@brief Dispatch subcommands.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(prog="acceptance", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("plan", "generate", "grade", "report"):
        p = sub.add_parser(name)
        if name != "report":
            p.add_argument("--rubric", type=Path, required=True)
        if name in ("plan", "generate"):
            p.add_argument("--models", nargs="+", required=True)
            p.add_argument("--replicates", type=int, default=1)
            p.add_argument("--seed", type=int, default=7)
        if name == "generate":
            p.add_argument("--repo", type=Path, required=True)
            p.add_argument("--out", type=Path, required=True)
            p.add_argument("--mcp-config", type=Path, default=None)
            p.add_argument("--timeout", type=int, default=1800)
        if name in ("grade", "report"):
            p.add_argument("--answers", type=Path, required=True)

    args = parser.parse_args()
    return {"plan": cmd_plan, "generate": cmd_generate, "grade": cmd_grade, "report": cmd_report}[
        args.cmd
    ](args)


if __name__ == "__main__":
    raise SystemExit(main())
