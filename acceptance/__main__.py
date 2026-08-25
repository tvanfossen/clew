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
from .grader.score import grader_fingerprint, score_question
from .runner import ARMS, check_revision, check_symmetry, parse_stem, plan


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
## @version 2
def cmd_plan(args) -> int:
    """@brief Show what a run would do.
    @return Exit code.
    @version 2
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    check_symmetry()
    cells = plan(rubric, tuple(args.models), args.replicates, args.seed)
    print(f"{rubric.target} @ {rubric.commit[:10]}  rubric {rubric.version}")
    print(f"digest {rubric.digest}  seed {args.seed}  {len(cells)} cells")
    for cell in cells:
        print(f"  {cell.order:>4}  {cell.stem()}")
    return 0


## @brief Run every cell and freeze its artifacts.
## @param args Parsed arguments.
## @return Exit code.
## @version 2
def cmd_generate(args) -> int:
    """PREFLIGHT BEFORE THE FIRST CELL, not per cell. A revision mismatch found on cell 40 has
    already spent 39 cells against the wrong tree.

    @brief Generate answers.
    @return Exit code.
    @version 2
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
                "rubric_digest": rubric.digest,
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
## @version 2
def cmd_grade(args) -> int:
    """Reads only the frozen `.md` files. A cell that failed left none, so it cannot be graded
    as an answer that said nothing.

    @brief Grade answers.
    @return Exit code.
    @version 2
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    questions = {q.id: q for q in rubric.questions}
    graded = 0
    for path in sorted(args.answers.glob("*.md")):
        parsed = parse_stem(path.stem)
        if parsed is None or parsed[0] not in questions:
            continue
        qid, arm = parsed[0], parsed[2]
        result = score_question(questions[qid], path.read_text("utf-8"), rubric, arm)
        got, unmarked = result.score()
        record = {
            "cell": path.stem,
            "arm": arm,
            "rubric_version": rubric.version,
            "rubric_digest": rubric.digest,
            "judge_model": rubric.judge_model,
            "score": got,
            "unmarked_pct": unmarked,
            ## DECISIONS THE JUDGE WAS NOT SURE OF. Not a drift predictor: measured,
            ## the cell that moved furthest on a regrade had none.
            "split_decisions": result.split_decisions(),
            ## WHICH GRADER PRODUCED THIS. Comparing passes across grader versions measures a
            ## code change and reads as judge noise — this session did exactly that.
            "grader_fingerprint": grader_fingerprint(),
            "decisions": [asdict(d) for d in result.decisions],
        }
        (args.answers / f"{path.stem}.grade.json").write_text(json.dumps(record, indent=2), "utf-8")
        ## APPENDED, BECAUSE GRADING USED TO EAT ITS OWN EVIDENCE. Regrading five cells against
        ## an unchanged rubric moved one by 12 points, and WHICH marks flipped is unrecoverable:
        ## the second pass overwrote the first. A variance figure needs both passes, and the
        ## decisions are the half that answers "what changed" rather than "how much".
        ##
        ## The sidecar above still holds the latest pass, so no consumer changes. Each line
        ## carries its own rubric digest, or a rubric edit between passes would be indexed as
        ## judge noise.
        with (args.answers / f"{path.stem}.grades.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"{path.stem:<34} score {got:6.1%}  unmarked {unmarked:5.1%}")
        graded += 1
    if not graded:
        print("no answers found — nothing was graded", file=sys.stderr)
        return 1
    return 0


## @brief Report the spread across grading passes, and which marks moved.
## @param answers Directory holding the frozen artifacts.
## @return None.
## @version 1
def _print_variance(answers: Path) -> None:
    """WHAT A REGRADE IS FOR. Grading five cells twice against an unchanged rubric moved one by
    12 points, and nothing could say which marks flipped because the second pass had overwritten
    the first. Passes are retained now; this reads them.

    A SPREAD ALONE IS NOT ENOUGH. "The cell moved 12 points" is the question and "these two marks
    flipped" is the answer, so the marks are named. A mark that held steady across every pass is
    omitted — listing it is noise in the one table built to isolate movement.

    ONLY PASSES SHARING A RUBRIC DIGEST ARE COMPARED, and the newest digest wins. A rubric edit
    between passes is a different question being answered; indexing that as variance would report
    a deliberate correction as instability, which is the mistake in the opposite direction.

    NOTHING IS PRINTED FOR A SINGLE PASS. A spread over one pass is zero, and printing zero
    asserts a stable grader on the strength of never having checked.

    @brief Cross-pass variance.
    @return None.
    @version 1
    """
    rows: list[tuple[str, list[dict]]] = []
    excluded: list[tuple[str, int, str]] = []
    for path in sorted(answers.glob("*.grades.jsonl")):
        passes = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                passes.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if not passes:
            continue
        ## THE GRADER IS PART OF THE COMPARISON, not just the rubric. This session measured a
        ## -12.1pt to +15.0pt spread on frozen answers and reported it as judge noise; it was
        ## the judge RETRY landing between the two grades, so marks previously left unruled
        ## started being ruled. Two passes under one grader version then reproduced every cell
        ## exactly. A code change measured as a property of the judge is the failure this pair
        ## of keys prevents.
        digest = passes[-1].get("rubric_digest")
        grader = passes[-1].get("grader_fingerprint")
        comparable = [
            p
            for p in passes
            if p.get("rubric_digest") == digest and p.get("grader_fingerprint") == grader
        ]
        ## ONE GUARD, NOT TWO. A `len(passes) < 2` skip stood here as well and was DEAD: this
        ## check already subsumes it, so no single edit could break either one and a mutation
        ## control reported the pair as untested. An exclusion enforced twice is an exclusion
        ## nothing verifies.
        if len(comparable) >= 2:
            rows.append((path.name.removesuffix(".grades.jsonl"), comparable))
        elif len(passes) >= 2:
            ## EXCLUDED, AND SAID SO. The fingerprint digests every grader source file, so an
            ## edit that cannot move a score still invalidates comparability — deliberately, a
            ## false "comparable" publishes a code change as judge noise. The cost is that an
            ## ordinary edit between passes leaves no variance row, and a reader seeing no row
            ## concludes there was no variance rather than that nothing was comparable.
            reason = (
                "grader" if len({p.get("grader_fingerprint") for p in passes}) > 1 else "rubric"
            )
            excluded.append((path.name.removesuffix(".grades.jsonl"), len(passes), reason))
    for cell, count, reason in excluded:
        print(
            f"\n{cell}: {count} pass(es) recorded, none comparable — they span more than one "
            f"{reason} version, so any spread between them would measure that change and not "
            f"the judge."
        )
    if not rows:
        return

    head = f"{'cell':<34} {'passes':>7} {'low':>8} {'high':>8} {'spread':>9}  marks that flipped"
    print(f"\n{head}")
    print("-" * len(head))
    by_arm: dict[str, list[float]] = {}
    for cell, passes in rows:
        scores = [float(p.get("score", 0.0)) for p in passes]
        low, high = min(scores), max(scores)
        by_arm.setdefault(str(passes[-1].get("arm", "?")), []).append((high - low) * 100)
        moved = sorted(
            {
                d["mark"]
                for p in passes
                for d in p.get("decisions", [])
                if any(
                    q["mark"] == d["mark"] and q.get("hit") != d.get("hit")
                    for other in passes
                    for q in other.get("decisions", [])
                )
            }
        )
        names = ", ".join(m[:44] for m in moved) if moved else "none"
        print(
            f"{cell:<34} {len(passes):>7} {low:>7.1%} {high:>7.1%} "
            f"{(high - low) * 100:>8.1f}pt  {names}"
        )
    ## PER ARM, BECAUSE ARM-DEPENDENT NOISE IS A BIAS AND NOT A FLOOR. Observed on three passes
    ## over five frozen cells: both baseline cells held at 0.0pt while all three index-arm cells
    ## moved 10-15pt. n=3 on five cells cannot distinguish that from chance, which is exactly why
    ## the number is PRINTED and nothing here rules on it — but if it holds, one shared error bar
    ## would understate one arm's uncertainty and overstate the other's, and every "the index
    ## wins by X" would need its own interval.
    ##
    ## The cell count rides with each mean. A mean over one cell is not a measurement, and
    ## printing it bare invites a reader to treat it as one.
    parts = [
        f"{arm} {sum(v) / len(v):.1f}pt ({len(v)} cell{'s' if len(v) != 1 else ''})"
        for arm, v in sorted(by_arm.items())
    ]
    print(f"mean spread by arm: {'  '.join(parts)}")
    print(
        "SPREAD is between grading passes of the SAME answers against the SAME rubric — it is the "
        "grader's\n        own noise, not a difference between arms. Passes graded against a "
        "different rubric digest are excluded."
    )


## @brief Print the per-cell table.
## @param rows (meta, grade) pairs in report order.
## @return None.
## @version 1
def _print_cells(rows: list) -> None:
    """EXTRACTED SO THE TABLE ITSELF IS TESTABLE. Every column here is a number a reader will
    quote, and a column that silently shifts or prints the wrong field is invisible in a
    coordinator function that also does file I/O.

    SPLIT counts verdicts whose judge samples disagreed. It does NOT predict drift — measured on
    five cells regraded against an unchanged rubric, three cells carrying a split reproduced
    exactly while the largest mover had none. It flags a decision the judge was unsure of, which
    is worth seeing on its own terms. An older sidecar predating the field prints as unknown
    rather than as zero, because zero would claim the judge never wavered.

    @brief Per-cell table.
    @return None.
    @version 1
    """
    head = (
        f"{'cell':<34} {'time':>7} {'out tok':>8} {'cache tok':>10} {'bytes':>8} "
        f"{'turns':>6} {'tools':>6} {'!idx':>5} {'deny':>5} {'score':>7} {'unmkd':>6} {'split':>6}"
    )
    print(head)
    print("-" * len(head))
    for meta, grade in rows:
        score = f"{grade['score']:6.1%}" if grade else "     —"
        unmarked = f"{grade['unmarked_pct']:5.1%}" if grade else "    —"
        split = str(grade.get("split_decisions", "—")) if grade else "—"
        print(
            f"{meta['stem']:<34} {meta['seconds']:6.1f}s {meta['output_tokens']:>8} "
            f"{meta['cache_read_tokens']:>10} {meta['result_bytes']:>8} {meta['turns']:>6} "
            f"{meta['tool_calls']:>6} {meta['non_index_tool_calls']:>5} "
            f"{meta['denied_tool_calls']:>5} {score:>7} {unmarked:>6} {split:>6}"
        )


## @brief Distinct files each question's marks cite, keyed by question id.
## @param rubric_path Rubric to read, or None when report was run without one.
## @return {question_id: distinct files cited}; empty when unavailable.
## @version 1
def _files_cited(rubric_path: Path | None) -> dict[str, int]:
    """THE OTHER HALF OF THE PREDICTION UNDER TEST. Separation alone cannot say whether the
    index's advantage is specific to answers assembled from places no single read reaches; the
    pair can, and n=1 over two saturated cells is the only evidence for it so far.

    A PROXY, AND SAID SO: citing four files does not prove an answer needs four reads. What it
    tracks is the shape that has actually saturated.

    RETURNS EMPTY RATHER THAN RAISING when the rubric is absent or unreadable. `report` reads a
    FINISHED run and must not fail on a rubric that has since moved or been re-versioned — the
    column degrades to unknown, which is what the caller prints.

    @brief Per-question citation spread.
    @return Mapping, possibly empty.
    @version 1
    """
    if rubric_path is None:
        return {}
    try:
        rubric = load(rubric_path)
    except RubricError:
        return {}
    return {
        q.id: len({str(ref[0]) for m in q.marks for ref in m.refs if ref}) for q in rubric.questions
    }


## @brief Report the three axes per cell, from frozen artifacts only.
## @param args Parsed arguments.
## @return Exit code.
## @version 2
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

    _print_cells(rows)
    _paired_summary(rows, files_cited=_files_cited(args.rubric))
    _print_variance(args.answers)
    print("\nOUT TOK and CACHE TOK are reported apart, never summed. Measured on one cell:")
    print(
        "534,192 cached against 7,292 output — a blended figure describes the prefix, not the work."
    )
    print("!idx = tool calls that did not use the index, the lever under test.")
    print("-1 in a tool column means the count could not be determined, NOT zero.")
    print("DENY on the BASELINE arm is contamination: it reached for a tool it should not see.")
    print(
        "SPLIT = verdicts whose judge samples disagreed — a decision the judge was unsure of, "
        "NOT a drift\n        predictor: regrading five cells, the one that moved furthest "
        "(-12.1pt) had no split verdicts at all."
    )
    print(
        "FILES = distinct files that question's marks cite, printed beside separation because "
        "multi-file\n        questions are where the index is predicted to excel. The harness "
        "prints the pair; it does not rule on it."
    )
    return 0


## @brief Per-question arm comparison: separation and shell displacement.
## @param rows (meta, grade) pairs for every cell in the run.
## @return None.
## @version 1
def _paired_summary(rows: list, files_cited: dict[str, int] | None = None) -> None:
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

    SPREAD RIDES BESIDE SEPARATION, because that pair is the prediction the grid exists to test:
    multi-file questions are where the index should excel over a source harness. Two saturated
    cells at n=1 suggested it and n=1 cannot establish it, so both numbers print on one row and
    NOTHING here rules on the correlation. `files_cited` is absent when `report` ran without a
    rubric and prints as unknown rather than as zero — a zero would be a claim about a rubric
    this process never opened.

    @brief Paired per-question summary.
    @return None.
    @version 2
    """
    files_cited = files_cited or {}
    paired: dict = {}
    for meta, grade in rows:
        parsed = parse_stem(str(meta["stem"]))
        if parsed is None:
            continue
        qid, model, arm, replicate = parsed
        ## KEYED ON THE PARSED ARM, not on meta["arm"]. They agree today, and a run whose
        ## metadata disagreed with its own filename would otherwise pair two cells of one arm.
        paired.setdefault((qid, model, replicate), {})[arm] = (meta, grade)

    ## DERIVED FROM `ARMS`, never hardcoded — the same defect `check_symmetry` already had, one
    ## file over. This named its two arms literally, so once the compared pair became
    ## baseline/index_only every cell failed the membership test and the whole block printed
    ## "No arm PAIRS in this run" on a grid where every cell WAS paired. Silent and total: the
    ## per-cell table still prints, so it reads like an unpaired run rather than a blind reporter.
    left, right = ARMS
    complete = {k: v for k, v in paired.items() if {left, right} <= set(v)}
    if not complete:
        print("\nNo arm PAIRS in this run — separation and displacement need both arms of a cell.")
        return

    print(
        f"\n{'question':<22} {'files':>6} {left:>9} {right:>9} {'separation':>11} "
        f"{'shell displaced':>16}"
    )
    print("-" * 77)
    for key in sorted(complete):
        b_meta, b_grade = complete[key][left]
        i_meta, i_grade = complete[key][right]
        label = f"{key[0]}_{key[1]}_r{key[2]}"
        ## UNKNOWN PRINTS AS UNKNOWN. Absent when report ran without a rubric; a 0 there would
        ## assert the question cites nothing, which is a claim about a file nobody opened.
        spread = str(files_cited.get(key[0], "—"))
        b_shell, i_shell = b_meta["non_index_tool_calls"], i_meta["non_index_tool_calls"]
        ## UNKNOWN COUNTS DO NOT BECOME A DISPLACEMENT. -1 means the transcript could not be
        ## read; arithmetic on it would invent a number.
        disp = "—" if b_shell < 0 or i_shell < 0 else f"{b_shell - i_shell:+d}"
        ## A CELL THE JUDGE NEVER RULED ON HAS NO SCORE TO COMPARE. Measured on the weekend
        ## grid: six cells came back with unmarked_pct 1.0 — every judge call failing rc=1 — and
        ## this table printed "0.0% 0.0% +0.0pt TIED" for them. A transport failure rendered as a
        ## finding about both arms, in the one table a reader draws conclusions from, on answers
        ## that were excellent.
        ##
        ## The design already says an unruled decision is not a miss. This enforces it where the
        ## comparison is actually made, at the threshold where most of a cell's weight went
        ## unruled — below that the score still means something and `unmkd` in the per-cell
        ## table carries the caveat.
        unruled = max(
            float((b_grade or {}).get("unmarked_pct", 0.0)),
            float((i_grade or {}).get("unmarked_pct", 0.0)),
        )
        if b_grade and i_grade and unruled > 0.5:
            print(
                f"{label:<22} {spread:>6} {'unruled':>9} {'unruled':>9} "
                f"{f'{unruled:.0%} unruled':>11} {disp:>16}"
            )
            continue
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
            print(f"{label:<22} {spread:>6} {b:>8.1%} {i:>8.1%} {sep:>11} {disp:>16}{flag}")
        else:
            print(f"{label:<22} {spread:>6} {'—':>9} {'—':>9} {'—':>11} {disp:>16}")
    ## A QUESTION MISSING FROM THIS TABLE LEAVES NO TRACE IN IT. Measured: a run held a baseline
    ## cell and a blended-arm cell for one question and no index_only cell, so that question
    ## simply did not appear — and a reader comparing five questions sees four rows with nothing
    ## saying why. Silent truncation reading as complete coverage is the shape this whole file
    ## exists to avoid, so what was dropped is named.
    unpaired = sorted({k[0] for k in paired} - {k[0] for k in complete})
    if unpaired:
        print(
            f"\n{len(unpaired)} question(s) had cells but no complete {left}/{right} pair and are "
            f"absent from the table above: {', '.join(unpaired)}."
        )
    tied = sum(
        1
        for k, v in complete.items()
        if v[left][1] and v[right][1] and abs(v[left][1]["score"] - v[right][1]["score"]) < 1e-9
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
        ## OPTIONAL FOR `report`, required everywhere else. A finished run's answers directory
        ## is self-describing for every other column, so requiring the rubric here would make a
        ## plain report impossible on a run whose rubric has since moved — and the one column it
        ## supplies degrades to unknown rather than to a wrong number.
        p.add_argument("--rubric", type=Path, required=name != "report", default=None)
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
