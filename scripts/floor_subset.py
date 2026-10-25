# SPDX-License-Identifier: MIT
"""Select the noise-floor subset reproducibly, and say what the selection excludes.

WHY THIS IS A COMMITTED SCRIPT. The 1.1.0 floor was chosen by an ad-hoc script in a gitignored
scratch directory, so the 21 cells could not be re-derived from the repository — a figure whose
method cannot be reproduced is one this project's own rule says to delete rather than re-derive.
The selection is deterministic given the run directory, so committing it makes the floor
reproducible without storing the cell list.

THE SELECTION IS DELIBERATELY BIASED AND THE BIAS IS CONSERVATIVE. Judge disagreement is largest
near the decision boundary, so sampling mid-range cells OVERSTATES the run-wide floor. For a
published result that is a LOSS, overstating the floor is the direction that argues against the
claim, which is why it is acceptable; the bias must still be stated wherever the floor is quoted.

@brief Pick a stratified mid-range subset for a second grading pass.
@version 1
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

## The score band a cell must fall in. A cell at 0 or 100 has little room to move, so a floor
## measured on ceiling cells reads lower than the truth.
LOW, HIGH = 20.0, 80.0

## A cell whose judge largely failed is measuring transport, not disagreement.
MAX_UNRULED = 0.2


## @brief The cells a run holds, with their first-pass score.
## @param answers A run target's answers directory.
## @return (distance from 50, stem, score) for every eligible cell.
## @version 1
def eligible(answers: Path) -> list[tuple[float, str, float]]:
    """@brief Eligible cells, closest to 50% first.
    @return Sortable candidate tuples.
    @version 1
    """
    out: list[tuple[float, str, float]] = []
    for f in sorted(answers.glob("*.grade.json")):
        g = json.loads(f.read_text())
        score = g["score"] * 100
        if LOW <= score <= HIGH and g["unmarked_pct"] < MAX_UNRULED:
            out.append((abs(score - 50.0), g["cell"], score))
    out.sort()
    return out


## @brief Copy a deterministic subset into a clean directory for an independent pass.
## @param run The run directory holding per-target answers.
## @param dest Where to write the subset.
## @param per_target How many cells to take from each target.
## @return Number of cells copied.
## @version 1
def build(run: Path, dest: Path, per_target: int) -> int:
    """SORTED BY DISTANCE FROM 50% AND THEN BY STEM, so ties break deterministically and two
    people running this on one run directory select the same cells.

    @brief Build the floor subset.
    @return Cell count.
    @version 1
    """
    if dest.exists():
        shutil.rmtree(dest)
    total = 0
    for target in sorted(p.name for p in run.iterdir() if (p / "answers").is_dir()):
        cands = eligible(run / target / "answers")
        chosen = sorted(cands[:per_target], key=lambda c: c[1])
        out = dest / target / "answers"
        out.mkdir(parents=True)
        for _, stem, score in chosen:
            shutil.copy(run / target / "answers" / f"{stem}.md", out / f"{stem}.md")
            print(f"{target:10} {stem:44} {score:5.1f}%")
            total += 1
        ## WHAT THE BAND EXCLUDED, reported rather than left implicit: the floor is quoted as a
        ## run-wide figure and it is not one.
        allc = [
            json.loads(f.read_text())["score"] * 100
            for f in (run / target / "answers").glob("*.grade.json")
        ]
        lo = sum(1 for s in allc if s < LOW)
        hi = sum(1 for s in allc if s > HIGH)
        print(f"{target:10} excluded {lo} cell(s) below {LOW:.0f}% and {hi} above {HIGH:.0f}%")
    return total


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """@brief Build a floor subset from a finished run.
    @return Exit code.
    @version 1
    """
    ap = argparse.ArgumentParser(prog="floor_subset", description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--per-target", type=int, default=7)
    args = ap.parse_args()
    n = build(args.run, args.dest, args.per_target)
    print(
        f"\n{n} cell(s) copied. Grade each target's directory with the SAME rubric to get pass 2."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
