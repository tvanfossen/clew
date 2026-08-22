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
    _paired_summary(rows)
    print("\nOUT TOK and CACHE TOK are reported apart, never summed. Measured on one cell:")
    print(
        "534,192 cached against 7,292 output — a blended figure describes the prefix, not the work."
    )
    print("!idx = tool calls that did not use the index, the lever under test.")
    print("-1 in a tool column means the count could not be determined, NOT zero.")
    print("DENY on the BASELINE arm is contamination: it reached for a tool it should not see.")
    return 0


## @brief Per-question arm comparison: separation and shell displacement.
## @param rows (meta, grade) pairs for every cell in the run.
## @return None.
## @version 1
def _paired_summary(rows: list) -> None:
    """TWO THINGS THE PER-CELL TABLE CANNOT SHOW, both of which decide whether a question earned
    its place in the grid.

    SEPARATION. A question where both arms score identically contributes nothing to the
    comparison however well its marks are written. Measured at n=1, three of four questions tied
    — one of them at 100%/100%, where the baseline reached the ceiling in four turns because the
    whole answer lived in one file. The discrimination fixtures cannot see that: a shallow answer
    and a complete one both score high on a saturated question and the gap looks healthy. Only
    two real arms tying reveals it, and only if someone reports it.

    DISPLACEMENT. The index arm still spends most of its calls on the shell, which invites the
    question of what the index is doing at all. The honest answer is per cell: how many shell
    calls did the baseline need, and how many did the index arm avoid. Measured, mbedtls Q1 traded
    3 index calls for 6 fewer shell calls and won 55 points; entropic Q2 spent 1 index call and
    made THREE MORE shell calls than the baseline.

    A NEGATIVE DISPLACEMENT IS A REAL RESULT, not a glitch: the index cost that cell more than it
    saved. Reporting only the wins is how a benchmark becomes a self-portrait.

    @brief Paired per-question summary.
    @return None.
    @version 1
    """
    paired: dict = {}
    for meta, grade in rows:
        parts = str(meta["stem"]).split("_")
        if len(parts) < 4:
            continue
        paired.setdefault((parts[0], parts[1], parts[3]), {})[meta["arm"]] = (meta, grade)

    complete = {k: v for k, v in paired.items() if {"baseline", "index"} <= set(v)}
    if not complete:
        print("\nNo arm PAIRS in this run — separation and displacement need both arms of a cell.")
        return

    print(
        f"\n{'question':<22} {'baseline':>9} {'index':>9} {'separation':>11} {'shell displaced':>16}"
    )
    print("-" * 70)
    for key in sorted(complete):
        b_meta, b_grade = complete[key]["baseline"]
        i_meta, i_grade = complete[key]["index"]
        label = f"{key[0]}_{key[1]}_{key[2]}"
        b_shell, i_shell = b_meta["non_index_tool_calls"], i_meta["non_index_tool_calls"]
        ## UNKNOWN COUNTS DO NOT BECOME A DISPLACEMENT. -1 means the transcript could not be
        ## read; arithmetic on it would invent a number.
        disp = "—" if b_shell < 0 or i_shell < 0 else f"{b_shell - i_shell:+d}"
        if b_grade and i_grade:
            b, i = b_grade["score"], i_grade["score"]
            sep = f"{(i - b) * 100:+.1f}pt" + ("" if abs(i - b) > 1e-9 else "  TIED")
            ## A CELL THAT NEVER TOUCHED THE INDEX IS NOT A RESULT ABOUT THE INDEX. Measured:
            ## one cell scored 16.7 points BELOW its baseline while making zero index calls.
            ## Read from the table alone that is a quality loss for the tool; it is in fact the
            ## adoption holdout, and the arm simply answered from source. Flagging it in the row
            ## is the difference between a reader drawing the right conclusion and the wrong one.
            idx_used = i_meta["tool_calls"] - i_meta["non_index_tool_calls"]
            flag = "" if i_meta["tool_calls"] < 0 or idx_used > 0 else "   NO INDEX CALLS"
            print(f"{label:<22} {b:>8.1%} {i:>8.1%} {sep:>11} {disp:>16}{flag}")
        else:
            print(f"{label:<22} {'—':>9} {'—':>9} {'—':>11} {disp:>16}")
    tied = sum(
        1
        for k, v in complete.items()
        if v["baseline"][1]
        and v["index"][1]
        and abs(v["baseline"][1]["score"] - v["index"][1]["score"]) < 1e-9
    )
    if tied:
        print(
            f"\n{tied} of {len(complete)} question(s) TIED. A tie contributes nothing to the "
            f"comparison — and a tie at the CEILING means the question is saturated and should be "
            f"replaced rather than averaged in."
        )


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
