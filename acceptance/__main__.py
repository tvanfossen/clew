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
    .venv/bin/python -m acceptance plan     --rubric <path> --models <DATED-ID> [--replicates 1]
    .venv/bin/python -m acceptance generate --rubric <path> --repo <tree> --out <dir> \\
                                            --models <DATED-ID> [--mcp-config <path>]
    .venv/bin/python -m acceptance grade    --rubric <path> --answers <dir>
    .venv/bin/python -m acceptance report   --answers <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .execute import index_cells_that_never_used_the_index, run_cell
from .grader.judge import JudgeCapacityError
from .grader.rubric import RubricError, load
from .identity import tool_identity
from .modelpin import require_pinned
from .grader.score import grader_fingerprint, score_question
from .runner import ARMS, check_revision, check_symmetry, parse_stem, plan


## @brief Load a rubric, refusing loudly rather than half-parsing.
## @param path Rubric path.
## @return Rubric, or None after printing the refusal.
## @version 1
def _rubric(path: Path):
    """THE JUDGE PIN IS ENFORCED HERE, NOT IN `grader/rubric.py`, AND THE REASON IS A DEFECT THIS
    PROJECT SHIPPED. `grader_fingerprint()` hashes every `*.py` under `acceptance/grader/`, so the
    1.1.1 release — which only refactored *input validation* in `rubric.py` — moved it from
    `9cc2b15baf93` to `18f7cfdb541c` and silently made the 144 published cells of
    `acceptance/runs/2026-10-19-n3/` un-re-gradable at their own keys. Nothing noticed: no
    preflight compares the two, `--skip-graded` reads a mismatch as a reason to grade rather than
    to refuse, and `.grade.json` is then overwritten unconditionally.

    Validating a model-id string is not scoring behaviour, so it does not belong in the hashed
    directory. `_rubric` is the single load point for every CLI path that produces a measurement —
    `plan`, `generate` and `grade` — which makes it the right place and keeps `grader/` byte-stable.

    **TWO LAYERS, DELIBERATELY, AND THE WEAKER ONE MUST NOT BE "TIDIED AWAY".** `rubric.load`
    still rejects a bare `sonnet`, by a rule that asks only for a hyphen and a digit — which
    `claude-haiku-5-5` satisfies, so it is not sufficient on its own. It is kept because
    strengthening it in place would move the fingerprint again, and it is useful as a refusal that
    reaches every loader including `python -m acceptance.grader.rubric`. The dated-id rule is this
    layer's job.

    `acceptance.grader.rubric`'s own CLI is deliberately NOT covered: it validates and prints a
    rubric's shape, produces no measurement, and already prints `judge:` so a reader sees an alias.

    @brief Load a rubric for the CLI, refusing an unpinned judge.
    @return Rubric or None.
    @version 2
    """
    try:
        rubric = load(path)
    except RubricError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return None
    try:
        require_pinned("judge.model", rubric.judge_model)
    except ValueError as exc:
        print(f"REFUSED — {path}: {exc}", file=sys.stderr)
        return None
    return rubric


## @brief Read the window records an earlier `generate` left in a run record.
## @param path Path to `run.json`.
## @return The recorded windows, oldest first; empty when there is no readable record.
## @version 1
def _prior_windows(path: Path) -> list:
    """A MISSING FILE AND AN UNREADABLE ONE ARE BOTH "NO PRIOR WINDOWS", and that is the only
    honest reading here — the alternative is refusing to generate because a record from a
    previous run is corrupt, which would strand the exact mid-run recovery `--resume` exists for.
    The new window is still appended and still numbered from what was found, so a damaged record
    loses history rather than silently renumbering as window 1 forever.

    A record written before this key existed has no `windows` — the 1.1.0 artifacts are in that
    shape — so it reads as no prior windows rather than raising on a frozen run.

    @brief Prior window records.
    @param path The run record path.
    @return The windows.
    @version 1
    """
    try:
        doc = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    windows = doc.get("windows")
    return list(windows) if isinstance(windows, list) else []


## @brief Refuse a run whose answering model is an alias rather than a dated id.
## @param models The model ids as given on the command line.
## @return True when every id is pinned; False after printing the refusal.
## @version 1
def _models_pinned(models) -> bool:
    """THE OTHER HALF OF THE EXPERIMENT. `grader/rubric.py` has refused an alias for the JUDGE
    since the first release, and nothing asked the same of the model being graded — so 1.1.0 was
    judged by `claude-sonnet-4-5-20250929` and answered by `claude-haiku-5-5`, and its artifacts
    claim a repeatability they do not have. One shared rule, one message, both halves.

    CHECKED ON `plan` AS WELL AS `generate`, because `plan` is what a human reads to decide
    whether to spend ten hours. Refusing at the point of spend would be correct and too late.

    @brief Are all answering models pinned.
    @param models The model ids.
    @return True when pinned.
    @version 1
    """
    try:
        for model in models:
            require_pinned("--models", str(model))
    except ValueError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return False
    return True


## @brief Print the ordered cell plan without running anything.
## @param args Parsed arguments.
## @return Exit code.
## @version 3
def cmd_plan(args) -> int:
    """@brief Show what a run would do.
    @return Exit code.
    @version 2
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    if not _models_pinned(args.models):
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
    @version 4
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    if not _models_pinned(args.models):
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

    ## THE FROZEN ANSWER IS THE RECORD, so resuming reads it rather than buying it again.
    ##
    ## OPT-IN. Without `--resume` a second `generate` re-spends every cell, which is what every
    ## past measurement assumed and what the artifacts of those runs mean. The flag exists
    ## because generation is serial and ~10 hours long: a capacity window in the middle loses
    ## its cells permanently, and reaching them again otherwise costs every completed cell a
    ## second time.
    ##
    ## `.md` IS THE RIGHT TEST, not the sidecars. `run_cell` writes it LAST and only when the
    ## agent produced text, so a cell that failed transport left `.meta.json` and `.raw.json`
    ## behind but no answer — and is correctly retried rather than skipped.
    resumed = sorted(c.stem() for c in cells if (args.out / f"{c.stem()}.md").is_file())
    if getattr(args, "resume", False):
        pending = [c for c in cells if c.stem() not in set(resumed)]
        print(f"resuming — {len(resumed)} cell(s) already answered, {len(pending)} to run")
    else:
        pending, resumed = cells, []

    ## ONE WINDOW PER `generate`, APPENDED — NEVER OVERWRITTEN. `resumed` recorded which stems
    ## were already answered, which is the right fact, but each resume REWROTE this file: after
    ## three capacity windows the record said "these cells came from before" and nothing at all
    ## about how many sittings there had been, when, or against which build. The 1.1.0 grid was
    ## assembled over several windows and its run.json can no longer say so.
    ##
    ## `tool_identity()` GOES IN THE WINDOW, not only at the top. It is the one thing that can
    ## legitimately DIFFER between windows — a dirty tree, a different commit, a rebuilt
    ## substrate — so a single top-level copy describes the last window and silently attributes
    ## it to all of them.
    ##
    ## ABSENT RATHER THAN EMPTY, as everywhere: a window that resumed nothing has no `resumed`
    ## key, so "started clean" and "nobody recorded" do not read alike.
    prior = _prior_windows(args.out / "run.json")
    window = {
        "ordinal": len(prior) + 1,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": list(args.models),
        "cells_pending": len(pending),
        **({"resumed": resumed} if resumed else {}),
        **tool_identity(),
    }

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
                ## WHAT ANSWERED, NOT ONLY WHAT WAS ASKED. Every other key here is an input to
                ## the measurement; these are the measurement's subject. `provision.json`
                ## carries the same fields beside the index, so a run whose provisioning
                ## record was lost is still attributable from the answers alone.
                **tool_identity(),
                ## WHICH CELLS CAME FROM AN EARLIER WINDOW. A grid assembled over several
                ## sittings must not read as one pass, and the stems are the only place that
                ## can be said. Absent rather than empty when nothing was resumed, so
                ## "assembled in one pass" and "nobody recorded" do not read alike.
                **({"resumed": resumed} if resumed else {}),
                ## THE HISTORY, not the latest view. Every key above describes this window; this
                ## one is the only place a grid assembled over several sittings can say so.
                "windows": [*prior, window],
                "cells": [asdict(c) for c in cells],
            },
            indent=2,
        ),
        "utf-8",
    )

    failed = 0
    results = []
    for cell in pending:
        result = run_cell(
            cell,
            prompts[cell.question_id],
            args.repo,
            args.out,
            args.mcp_config,
            args.timeout,
            skills=getattr(args, "skills", None),
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
    print(f"\n{len(pending) - failed}/{len(pending)} cells produced an answer")
    blind = index_cells_that_never_used_the_index(results)
    if blind:
        print(
            f"\nWARNING — {len(blind)} index cell(s) made ZERO index calls: {blind}\n"
            f"That is what an index arm running WITHOUT its index looks like: the server starts, "
            f"finds no database, registers no query tools, and the agent answers from the source "
            f"with no error anywhere. Verify the MCP config resolves before trusting these cells."
        )
    return 1 if failed else 0


## @brief Yield each worker's line as it finishes rather than in submission order.
## @param pool The executor.
## @param fn The per-item callable.
## @param items The items to process.
## @return An iterator of results, in completion order.
## @version 1
def as_completed_lines(pool, fn, items):
    """SPLIT OUT SO THE PROGRESS RULE IS TESTABLE ON ITS OWN. Inline, the only way to assert
    that grading reports as it goes was to drive the whole command.

    @brief Results in completion order.
    @return Iterator of results.
    @version 1
    """
    futures = [pool.submit(fn, item) for item in items]
    for future in as_completed(futures):
        yield future.result()


## @brief How many passes a cell already holds at the CURRENT rubric and grader version.
## @param answers The answers directory.
## @param stem The cell's filename stem.
## @param digest The rubric digest a pass must carry to count.
## @param fingerprint The grader fingerprint a pass must carry to count.
## @return The number of matching passes already recorded.
## @version 1
def passes_recorded(answers: Path, stem: str, digest: str, fingerprint: str) -> int:
    """A PASS FROM A DIFFERENT GRADER IS NOT A PASS AT THIS VERSION — the same rule
    `_print_variance` already applies when it refuses to compare across fingerprints. Counting
    one would skip a cell whose only verdict came from code that no longer exists, leaving a
    hole that reads as coverage.

    THE RUBRIC DIGEST COUNTS FOR THE SAME REASON: a rubric edited between windows means the
    earlier verdict answered a different question.

    An unreadable or absent history is ZERO, never "probably fine". The cost of regrading a cell
    that was already done is one cell; the cost of skipping one that was not is a hole.

    @brief Matching passes already on disk.
    @return Pass count.
    @version 1
    """
    history = answers / f"{stem}.grades.jsonl"
    if not history.is_file():
        return 0
    count = 0
    try:
        for line in history.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("rubric_digest") == digest and row.get("grader_fingerprint") == fingerprint:
                count += 1
    except OSError:
        return 0
    return count


## @brief Grade every frozen answer against the rubric.
## @param args Parsed arguments.
## @return Exit code.
## @version 2
def cmd_grade(args) -> int:
    """Reads only the frozen `.md` files. A cell that failed left none, so it cannot be graded
    as an answer that said nothing.

    @brief Grade answers.
    @return Exit code.
    @version 5
    """
    rubric = _rubric(args.rubric)
    if rubric is None:
        return 1
    questions = {q.id: q for q in rubric.questions}

    ## @brief Grade one frozen answer and write its two sidecars.
    ## @param path The answer file.
    ## @return The line to print, or None when the stem is not a gradeable cell.
    ## @version 1
    def _grade_one(path: Path) -> str | None:
        """ONE ANSWER, ITS OWN TWO FILES, NO SHARED STATE — which is what makes `--jobs` safe
        rather than merely faster. Each call reads one `.md` and writes only `<stem>.grade.json`
        and `<stem>.grades.jsonl`, so concurrent workers never touch the same path.

        PRINTING IS THE CALLER'S JOB. A worker printing as it finishes interleaves the log in
        completion order, and a log whose order depends on scheduling cannot be diffed between
        passes.

        @brief Grade one answer.
        @return Its log line, or None.
        @version 1
        """
        parsed = parse_stem(path.stem)
        if parsed is None or parsed[0] not in questions:
            return None
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
        return f"{path.stem:<34} score {got:6.1%}  unmarked {unmarked:5.1%}"

    ## CONCURRENT ONLY WHEN ASKED, AND THE ORDER OF THE LOG NEVER MOVES. The answers are graded
    ## in whatever order slots free up, but `map` yields results in submission order, so the
    ## printed pass reads identically at any `--jobs` and two passes stay diffable.
    ##
    ## A FULL GRID IS ~3,400 JUDGE CALLS PER PASS and the noise floor needs two of them, so
    ## serial grading is most of a run's wall-clock while contributing to no reported axis.
    ## Generation stays serial for the opposite reason: a cell's wall-clock IS a reported axis.
    paths = sorted(args.answers.glob("*.md"))
    jobs = max(1, int(getattr(args, "jobs", 1) or 1))

    ## WITHOUT THIS A CAPACITY-LIMITED ACCOUNT CANNOT FINISH A GRID. Grading every `.md` every
    ## time means each capacity window spends most of its budget redoing work: measured on the
    ## 1.1.0 run, one window graded entropic's first 23 cells, the next RE-graded those 23 and
    ## reached 30, and two targets were never touched. The frontier moved about seven cells per
    ## window against 144 cells needing two passes each.
    ##
    ## OPT-IN, like `--resume`. With no flag a second `grade` still re-grades everything, which
    ## is how the noise floor is collected and what every earlier pass did. With it, completion
    ## is two ordered sweeps that only ever move forward: `--skip-graded 1` brings every cell to
    ## one pass, `--skip-graded 2` to two.
    want = int(getattr(args, "skip_graded", 0) or 0)
    if want > 0:
        fingerprint = grader_fingerprint()
        before = len(paths)
        paths = [
            path
            for path in paths
            if passes_recorded(args.answers, path.stem, rubric.digest, fingerprint) < want
        ]
        print(
            f"skipping {before - len(paths)} cell(s) already at {want} pass(es); "
            f"{len(paths)} to grade"
        )

    ## PRINTED AS EACH CELL LANDS, NEVER COLLECTED AND FLUSHED AT THE END. A pass is thousands
    ## of judge calls and the noise floor needs two of them, so a log that stays silent until
    ## the last cell cannot be told from a hang — which is the failure `matrix.py` already
    ## carries a line-buffering comment about. Collecting the lines first to keep them in
    ## submission order reintroduced it, on the serial path as well as the parallel one.
    ##
    ## SO THE ORDER GIVES WAY INSTEAD OF THE PROGRESS. Under `--jobs` the lines arrive as
    ## workers finish rather than in filename order, and that is fine: every line NAMES ITS OWN
    ## CELL, so comparing two passes is a sort away. A missing progress signal is not
    ## recoverable by sorting.
    graded = 0

    def _emit(line: str | None) -> None:
        nonlocal graded
        if line is None:
            return
        print(line)
        graded += 1

    ## A CAPACITY REFUSAL ENDS THE PASS, AND SAYS SO. Every remaining call would fail the same
    ## way, so continuing spends the rest of the grid discovering that repeatedly and writes a
    ## hole into each cell it touches. Grading is additive, so the cells already written stand
    ## and a later pass fills the rest — which makes stopping cheap and continuing expensive.
    aborted = ""
    try:
        if jobs == 1:
            for path in paths:
                _emit(_grade_one(path))
        else:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                for line in as_completed_lines(pool, _grade_one, paths):
                    _emit(line)
    except JudgeCapacityError as exc:
        aborted = str(exc)

    if aborted:
        print(
            f"\nSTOPPED after {graded} cell(s) — {aborted}",
            file=sys.stderr,
        )
        return 2

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
    ##
    ## IT THEN UNPACKED EXACTLY TWO, so adding the blended arm would have raised ValueError from
    ## the reporter. The first arm is the REFERENCE every other arm is measured against, and
    ## each comparison gets its OWN ROW rather than another pair of columns — a table that grows
    ## sideways with the arm count stops being readable at three.
    reference, *compared = ARMS
    complete = {k: v for k, v in paired.items() if set(ARMS) <= set(v)}
    if not complete:
        print(
            f"\nNo complete arm SETS in this run — separation needs {reference} and "
            f"{', '.join(compared)} for the same cell."
        )
        return

    print(
        f"\n{'question':<22} {'files':>6} {'arm':<11} {reference:>9} {'arm':>9} "
        f"{'separation':>11} {'shell displaced':>16}"
    )
    print("-" * 89)
    for key in sorted(complete):
        for arm in compared:
            _separation_row(key, arm, reference, complete[key], files_cited)
    _name_incomplete(paired, complete, reference, compared)
    return


## @brief Print one reference-versus-arm comparison row.
## @param key The (question, model, replicate) this row describes.
## @param arm The comparison arm.
## @param reference The arm every other is measured against.
## @param cells That cell's per-arm (meta, grade) pairs.
## @param files_cited Files cited per question, or empty when no rubric was given.
## @return None.
## @version 1
def _separation_row(key, arm: str, reference: str, cells: dict, files_cited: dict) -> None:
    """ONE ROW PER COMPARISON, so the table grows DOWN with the arm count rather than across.

    @brief One separation row.
    @return None.
    @version 1
    """
    if True:
        b_meta, b_grade = cells[reference]
        i_meta, i_grade = cells[arm]
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
                f"{label:<22} {spread:>6} {arm:<11} {'unruled':>9} {'unruled':>9} "
                f"{f'{unruled:.0%} unruled':>11} {disp:>16}"
            )
            return
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
            print(
                f"{label:<22} {spread:>6} {arm:<11} {b:>8.1%} {i:>8.1%} {sep:>11} {disp:>16}{flag}"
            )
        else:
            print(f"{label:<22} {spread:>6} {arm:<11} {'—':>9} {'—':>9} {'—':>11} {disp:>16}")


## @brief Name the questions that did not produce a complete arm set, and the ties.
## @param paired Every cell seen, keyed by (question, model, replicate).
## @param complete Those holding every arm.
## @param reference The reference arm.
## @param compared The arms measured against it.
## @return None.
## @version 1
def _name_incomplete(paired: dict, complete: dict, reference: str, compared: list) -> None:
    """A QUESTION MISSING FROM THE TABLE LEAVES NO TRACE IN IT. Measured: a run held a baseline
    cell and a blended-arm cell for one question and no index_only cell, so that question simply
    did not appear — and a reader comparing five questions sees four rows with nothing saying
    why. Silent truncation reading as complete coverage is the shape this file exists to avoid.

    @brief Name what the table left out.
    @return None.
    @version 1
    """
    arms = [reference, *compared]
    missing = sorted({k[0] for k in paired} - {k[0] for k in complete})
    if missing:
        print(
            f"\n{len(missing)} question(s) had cells but no complete "
            f"{'/'.join(arms)} set and are absent from the table above: {', '.join(missing)}."
        )
    tied = 0
    for cells in complete.values():
        ref = cells[reference][1]
        if not ref:
            continue
        for arm in compared:
            other = cells[arm][1]
            if other and abs(ref["score"] - other["score"]) < 1e-9:
                tied += 1
    if tied:
        print(
            f"\n{tied} of {len(complete) * len(compared)} comparison(s) TIED. A tie contributes "
            f"nothing — and a tie at the CEILING means the question is saturated and should be "
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
            p.add_argument(
                "--resume",
                action="store_true",
                help="skip cells whose answer is already frozen on disk",
            )
            ## A USAGE DOCUMENT APPENDED TO THE SYSTEM PROMPT, not to the brief. The brief is
            ## what `check_symmetry` guards; varying it would rebuild the coached-versus-
            ## uncoached asymmetry an earlier run was thrown out for.
            p.add_argument(
                "--skills",
                type=Path,
                default=None,
                help="usage document to append to the agent's system prompt",
            )
        if name in ("grade", "report"):
            p.add_argument("--answers", type=Path, required=True)
        if name == "grade":
            ## GRADING MAY PARALLELISE AND GENERATION MAY NOT, and the reason is which axes are
            ## measured. A cell's wall-clock IS a reported result, so running cells concurrently
            ## would contaminate it; a judge call's wall-clock is reported nowhere. The judge
            ## already retries with backoff, which is what absorbs the added rate pressure.
            p.add_argument("--jobs", type=int, default=1, help="judge this many answers at once")
            p.add_argument(
                "--skip-graded",
                type=int,
                default=0,
                metavar="N",
                help="skip cells already holding N passes at this rubric and grader version",
            )

    args = parser.parse_args()
    return {"plan": cmd_plan, "generate": cmd_generate, "grade": cmd_grade, "report": cmd_report}[
        args.cmd
    ](args)


if __name__ == "__main__":
    raise SystemExit(main())
