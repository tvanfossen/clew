# SPDX-License-Identifier: MIT
"""THE POST-RELEASE REVIEW'S FIRST THREE STEPS, as a command rather than as a habit.

`acceptance/DESIGN.md` ("Post-release review: read the cells, not the mean") specifies six steps
and then says of this part: *"The call-tracing and mark-classification steps were hand-rolled and
belong in `scripts/` before the next release, so the procedure does not have to be re-derived from
this section."* This is that. `scripts/selector_waste.py` is the counting half and
`scripts/served_spelling_audit.py` the attribution half; between them the review reads frozen
artefacts only, costs no judge calls and no generation, and is re-runnable on any published grid.

TWO SUBCOMMANDS, MATCHING TWO STEPS.

`rank` is step 1 — **rank by the index-vs-baseline GAP, not by raw score**, because a cluster every
arm fails measures the RUBRIC and not the tool. It prints the paired per-arm shape beside the gap:
answer length, tool calls, and the failed weight. That pairing is the whole reason it exists. A
correlation taken across ALL cells says cells with few calls score HIGHER, which is confounded by
difficulty — an easy question needs few calls and scores well. Paired WITHIN a cluster the
confound is controlled, and the 1.1.0 grid then says the opposite: on the worst clusters the index
arm made FEWER calls than the shell arm (entropic Q4 13.0 -> 5.3, self Q3 9.0 -> 3.7, mbedtls Q3
11.0 -> 6.3) while scoring 20-28 points lower. That reading is what reclassified a whole block of
failures from "the answer was thin" to "the retrieval round-tripped and the agent gave up", and it
is invisible in any unpaired view.

`trace` is step 3 — **the agent's actual call sequence AND every reply**. The call list alone is
not enough; what came back is where the cause lives. `search(corpus="files", text="llama")`
returning `count=0` in a repository holding seven `llama_cpp_*` files is invisible unless the
reply is read.

WHERE THE PER-CALL DETAIL LIVES, AND WHY THAT IS FRAGILE. A run directory holds the final answer,
the grade sidecars and a usage envelope — **no tool blocks at all**. The calls and replies are in
the CLI's own session transcript under `~/.claude/projects/<slug>/<session_id>.jsonl`, reachable
only because `.raw.json` records the `session_id`. So the most diagnostic artefact of a published
run is the one artefact the run does not contain, and a culled transcript takes the review with
it. Checked at the time of writing: all 48 `index_only` cells of `2026-10-19-n3` still resolve.
That is worth knowing before a review is planned around it, and it is why every unreadable cell is
NAMED rather than skipped.

Usage:
    .venv/bin/python scripts/cluster_review.py rank  acceptance/runs/<date>/
    .venv/bin/python scripts/cluster_review.py trace acceptance/runs/<date>/ entropic Q4
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from selector_waste import _blocks  # noqa: E402

PROJECTS = Path.home() / ".claude" / "projects"
CELL = re.compile(r"^(Q\d+)_(.+?)_(baseline|index_only|index)_r(\d+)$")

## The arm the hypothesis is judged on, per the owner ruling recorded in `acceptance/DESIGN.md`:
## `index_only` measures what the tool makes POSSIBLE, while `index` measures whether a
## grep-trained model chooses well, which is a fact about the model.
PRIMARY_ARM = "index_only"


##
# @brief Every target directory of a run that holds answers.
# @param run The run root.
# @return Target directory names, sorted.
# @version 1
def targets_of(run: Path) -> list[str]:
    """@brief List a run's answer-bearing targets.
    @return The target names.
    @version 1
    """
    return sorted(p.name for p in run.iterdir() if (p / "answers").is_dir())


##
# @brief One cell's score, answer length, call count and failed weight.
# @param adir The target's answers directory.
# @param stem The cell stem.
# @return (score pct, answer chars, tool calls, failed weight, total weight).
# @version 1
def cell_shape(adir: Path, stem: str) -> tuple[float, int, int, int, int]:
    """FAILED WEIGHT IS DE-DUPLICATED BY MARK TEXT, because replicates repeat every decision and
    summing them counts one mark three times. A mark that any replicate HIT is counted as hit —
    the pessimistic direction would make a flaky judge look like a capability gap.

    `-1` IS RETURNED FOR AN ABSENT MEASUREMENT, never 0, for the reason the vocabulary states
    about `tool_calls`: unknown must not be counted as none.

    @brief Read one cell's shape from its sidecars.
    @return The tuple.
    @version 1
    """
    grade = json.loads((adir / f"{stem}.grade.json").read_text("utf-8"))
    by_mark: dict[str, bool] = {}
    for d in grade.get("decisions", []):
        by_mark[d["mark"]] = by_mark.get(d["mark"], False) or bool(d.get("hit"))
    weights = {d["mark"]: d.get("weight", 1) for d in grade.get("decisions", [])}
    failed = sum(w for m, w in weights.items() if not by_mark.get(m))
    md = adir / f"{stem}.md"
    meta = adir / f"{stem}.meta.json"
    chars = len(md.read_text("utf-8")) if md.exists() else -1
    calls = -1
    if meta.exists():
        calls = json.loads(meta.read_text("utf-8")).get("tool_calls", -1)
    return grade["score"] * 100, chars, calls, failed, sum(weights.values())


##
# @brief Rank every cluster by the primary arm's gap against baseline.
# @param run The run root.
# @return Process exit status.
# @version 1
def rank(run: Path) -> int:
    """STEP 1 OF THE PROCEDURE, with the paired shape beside it. See the module docstring for why
    the pairing is the point rather than a decoration.

    A cluster with no baseline arm is SKIPPED AND NAMED, not ranked against nothing: a gap needs
    both halves, and ranking a one-armed cluster at its raw score is the "cluster every arm fails"
    error the step exists to avoid.

    @brief Print the gap-ranked cluster table.
    @return 0, or 2 when no cluster could be paired.
    @version 1
    """
    shapes: dict[tuple[str, str, str], list[tuple[float, int, int, int, int]]] = defaultdict(list)
    for target in targets_of(run):
        adir = run / target / "answers"
        for grade in sorted(adir.glob("*.grade.json")):
            stem = grade.name[: -len(".grade.json")]
            m = CELL.match(stem)
            if not m:
                continue
            q, _model, arm, _rep = m.groups()
            shapes[(target, q, arm)].append(cell_shape(adir, stem))

    rows = []
    unpaired = []
    for (target, q, arm), vals in shapes.items():
        if arm != PRIMARY_ARM:
            continue
        base = shapes.get((target, q, "baseline"))
        if not base:
            unpaired.append(f"{target} {q}")
            continue
        mean = lambda vs, i: statistics.mean(v[i] for v in vs)  # noqa: E731
        rows.append(
            (
                mean(vals, 0) - mean(base, 0),
                target,
                q,
                mean(vals, 0),
                mean(base, 0),
                mean(vals, 2),
                mean(base, 2),
                mean(vals, 1),
                mean(base, 1),
                mean(vals, 3),
                mean(vals, 4),
            )
        )
    if not rows:
        print(f"no cluster in {run} has both {PRIMARY_ARM} and baseline cells")
        return 2
    rows.sort()
    print(f"run: {run}   primary arm: {PRIMARY_ARM}   clusters: {len(rows)}\n")
    print(
        f"{'gap':>7}  {'cluster':<14} {'score':>12}  {'tool calls':>12}  "
        f"{'answer chars':>14}  {'failed wt':>10}"
    )
    print(f"{'':>7}  {'':<14} {'idx':>5}{'base':>7}  {'idx':>5}{'base':>7}  {'idx':>6}{'base':>8}")
    for gap, target, q, io, b0, ic, bc, ich, bch, fw, tw in rows:
        print(
            f"{gap:+7.2f}  {target + ' ' + q:<14} {io:5.1f}{b0:7.1f}  "
            f"{ic:5.1f}{bc:7.1f}  {ich:6.0f}{bch:8.0f}  {fw:4.0f}/{tw:<5.0f}"
        )
    ## NAMED, NOT SUMMARISED. A cluster left out of a ranking is a cluster the review did not
    ## cover, and "25 clusters ranked" beside a silent omission is the flattering reading.
    if unpaired:
        print(f"\nunpaired (no baseline arm, NOT ranked): {len(unpaired)}")
        for name in unpaired:
            print(f"  {name}")
    return 0


##
# @brief Print one cluster's call-and-reply trace, per replicate.
# @param run The run root.
# @param target The target name.
# @param question The question id.
# @return Process exit status.
# @version 1
def trace(run: Path, target: str, question: str) -> int:
    """STEP 3 OF THE PROCEDURE. Paired by `tool_use` id through `selector_waste._blocks`, so a
    transcript that repeats a row shows one call — the inflation that put 157 in a draft where
    `selector_waste.py` counts 92.

    THE REPLY IS SIZED AND FLAGGED RATHER THAN PRINTED WHOLE. A single cell's replies run to 54 KB
    and the thing a reviewer needs first is the SHAPE: which calls came back empty, and how big the
    one before the agent stopped was. Reading a specific reply in full is then a one-line jq away,
    and the trace names the transcript so it can be.

    @brief Trace one cluster's calls and replies.
    @return 0, or 2 when no transcript resolves.
    @version 1
    """
    adir = run / target / "answers"
    raws = sorted(adir.glob(f"{question}_*{PRIMARY_ARM}*.raw.json"))
    if not raws:
        print(f"no {PRIMARY_ARM} cells for {target} {question} in {run}")
        return 2
    resolved = 0
    for raw in raws:
        session = json.loads(raw.read_text("utf-8")).get("session_id")
        hits = sorted(PROJECTS.glob(f"*/{session}.jsonl")) if session else []
        stem = raw.name[: -len(".raw.json")]
        if not hits:
            ## A CULLED TRANSCRIPT IS NAMED. It is the artefact a published run does not carry,
            ## so its absence is the expected failure here and must not read as a quiet cell.
            print(f"\n=== {stem}: NO TRANSCRIPT (session {session})")
            continue
        resolved += 1
        uses, results = _blocks(hits[0])
        print(f"\n=== {stem}   calls={len(uses)}   transcript={hits[0].name}")
        for call_id, block in uses.items():
            name = str(block.get("name") or "").replace("mcp__clew__", "")
            args = json.dumps(block.get("input") or {})
            reply = results.get(call_id, "")
            miss = '"found": false' in reply or '"found":false' in reply
            print(f"  CALL  {name}({args[:150]})")
            print(f"  REPLY {len(reply):>7} bytes  {'MISS' if miss else 'hit'}")
    return 0 if resolved else 2


##
# @brief Dispatch a subcommand.
# @return Process exit status.
# @version 1
def main(argv: list[str]) -> int:
    """@brief Route `rank` / `trace`.
    @return The subcommand's status, or 1 on a usage error.
    @version 1
    """
    if len(argv) >= 2 and argv[0] == "rank":
        return rank(Path(argv[1]))
    if len(argv) >= 4 and argv[0] == "trace":
        return trace(Path(argv[1]), argv[2], argv[3])
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
