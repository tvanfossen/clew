# SPDX-License-Identifier: MIT
## @brief Is the grading pass COMPLETE, or merely finished running?
## @version 2
"""`unmarked_pct` is the number that says whether a score means anything, and it has to be
checked from the SIDECARS rather than from a run log.

WHY THIS IS A TRACKED SCRIPT. It began as a throwaway probe in the session scratchpad and was
lost twice when the session directory rotated — the same mistake, in miniature, that lost the
raw data of an earlier grid. The sidecars survived both times because they live in the repo.
Anything used to decide whether a measurement is trustworthy belongs beside the measurement,
not in a temp directory.

WHY IT MATTERS AT ALL. `JUDGE_ERROR` weighs 0.0 in the score, arithmetically identical to "the
judge ruled MISS". A grading pass interrupted by session capacity therefore produces a
plausible-looking score built from a fraction of its marks — 102 of 324 on one earlier run, 449
of 1,026 on another. Neither was visible in the score itself.

A cell holding ANY judge error is treated as unfinished, so `grade_matrix complete` re-grades
it on the next invocation. This script reports what remains.

Usage:
  .venv/bin/python acceptance/bench/grading_coverage.py <answers-dir> [<answers-dir> ...]

Exit code is 0 only when every graded cell is fully ruled AND there was something to rule on.
An empty or missing directory is an ERROR, not a pass: this script exited 0 with
"COMPLETE — every graded cell fully ruled" when pointed at a directory holding no sidecars at
all, which is the reassurance without the measurement.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


## @brief Coverage figures for one run directory.
## @param root Directory holding `*.grade.json` sidecars.
## @return Dict of cells/marks/errors plus the per-cell error histogram.
## @version 1
def coverage(root: Path) -> dict:
    """Reads sidecars only. Deliberately does NOT consult a run log: a log is a narrative of
    what a process did, while the sidecars are what a consumer would actually score.

    @brief Summarise grading completeness for one target.
    @return Coverage record.
    @version 1
    """
    cells = clean = marks = errors = bonus_errors = 0
    histogram: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    keys: collections.Counter = collections.Counter()
    for path in sorted(root.glob("*.grade.json")):
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            reasons["unreadable sidecar"] += 1
            continue
        summary = sidecar.get("summary", {})
        keys[sidecar.get("rubric_version") or "<unrecorded>"] += 1
        cells += 1
        marks += summary.get("marks_total", 0)
        errs = summary.get("judge_errors", 0)
        ## BONUS ERRORS COUNTED SEPARATELY BUT COUNTED. This script read `summary` only and
        ## iterated `sidecar["marks"]` only, so an unruled BONUS mark was invisible to the one
        ## check whose entire job is spotting unruled marks. Measured, not theorised: a source
        ## baseline was documented as fully ruled at `unmarked_pct 0.0%` while one of its
        ## sidecars carried `bonus_summary.judge_errors: 2`, and this printed "... COMPLETE".
        ## A check that cannot see part of its input reports nothing, which is
        ## indistinguishable from passing.
        ##
        ## They stay OUT of `unmarked_pct`, which is defined over the marks that make up the
        ## score, and they still make the cell degraded — an unruled mark is unmeasured
        ## whichever list it is filed under.
        bonus_errs = sidecar.get("bonus_summary", {}).get("judge_errors", 0)
        errors += errs
        bonus_errors += bonus_errs
        histogram[errs + bonus_errs] += 1
        clean += errs + bonus_errs == 0
        for mark in (*sidecar.get("marks", []), *sidecar.get("bonus", [])):
            reason = (mark.get("judge") or {}).get("judge_error")
            if reason:
                reasons[reason[:60]] += 1
    return {
        "cells": cells, "clean": clean, "degraded": cells - clean,
        "marks": marks, "errors": errors, "bonus_errors": bonus_errors,
        "unmarked_pct": round(100.0 * errors / marks, 1) if marks else 0.0,
        "histogram": dict(sorted(histogram.items())), "reasons": reasons,
        ## WHICH GRADING KEY PRODUCED THESE GRADES, counted per version rather than assumed.
        ## A directory holding two rubric versions is two measurements reported as one, and
        ## that is the failure a PARTIAL re-grade introduces: the cells all look graded, the
        ## per-question scores all look comparable, and half of them answer a different key.
        ## Absent counts as its own version (`<unrecorded>`) because "no key recorded" is a
        ## distinct state from any key, not a wildcard that matches all of them.
        "rubric_versions": dict(keys),
    }  # fmt: skip


## @brief Print one target's coverage.
## @param name Directory name, used as the label.
## @param data Coverage record.
## @return None.
## @version 1
## @dg_internal
def _report(name: str, data: dict) -> None:
    """@brief Render a coverage record.
    @version 1
    """
    print(f"\n=== {name} ===")
    print(
        f"  cells graded : {data['cells']}   fully ruled: {data['clean']}   "
        f"degraded: {data['degraded']}"
    )
    print(
        f"  marks        : {data['marks']}   unruled: {data['errors']}   "
        f"unmarked_pct: {data['unmarked_pct']}%"
    )
    ## Printed on EVERY run, not only when non-zero. A line that appears only on failure
    ## teaches a reader that its absence means nothing was checked.
    print(f"  bonus        : unruled: {data['bonus_errors']}")
    census = data["rubric_versions"]
    print(f"  rubric key    : {', '.join(f'{v} x{n}' for v, n in sorted(census.items()))}")
    if data["degraded"]:
        print(f"  errors per cell: {data['histogram']}")
        for reason, count in data["reasons"].most_common(3):
            print(f"    {count:>5}  {reason}")


## @brief Why a directory's grades cannot be aggregated, or "" when they can.
## @param data Coverage record.
## @return Reason string naming the conflicting keys, else "".
## @version 1
## @dg_internal
def _mixed_keys(data: dict) -> str:
    """MIXED IS FATAL, UNIFORM IS NOT — including uniformly unrecorded. This gates the specific
    hazard a re-grade creates rather than auditing history: re-grade some cells of a directory
    onto a new key and the per-question scores stop being comparable to each other, while every
    cell still reads as fully graded. That is a silent aggregation of two measurements, the same
    shape as counting an unruled mark as a MISS.

    A wholly legacy directory reads `<unrecorded> xN` and passes, because failing it would gate
    every historical arm on a field that did not exist when it was graded — and a gate that
    fires on unrelated old data is the kind that gets disarmed. It is REPORTED on every run
    regardless, which is what makes the state visible without making it fatal.

    @brief Detect a directory holding more than one grading key.
    @return Reason, or "".
    @version 1
    """
    census = data["rubric_versions"]
    if len(census) < 2:
        return ""
    shown = ", ".join(f"{v} x{n}" for v, n in sorted(census.items()))
    return (
        f"grades from {len(census)} different rubric versions in one directory ({shown}) — "
        "a score aggregated across two grading keys is not one measurement. Re-grade the "
        "remainder, or split the arms into separate directories."
    )


## @brief Why a directory cannot be reported on at all, or "" when it can.
## @param root Resolved directory to check.
## @param data Coverage record, or None when the directory does not exist.
## @return A reason string for an unmeasurable input, else "".
## @version 2
## @dg_internal
def _unmeasurable(root: Path, data: dict | None) -> str:
    """NOTHING GRADED IS NOT THE SAME AS EVERYTHING RULED, and this script used to conflate
    them: pointed at an empty directory it printed "COMPLETE — every graded cell fully ruled"
    and exited 0, because zero cells means zero degraded cells. It is the documented step for
    "verify coverage before believing any score", so a green light on no data is worse than no
    check — it is the reassurance without the measurement, the same shape as a `JUDGE_ERROR`
    weighing exactly what a genuine MISS weighs.

    A cell with zero MARKS counts as unmeasurable for the same reason: `unmarked_pct` is
    `errors / marks` and reads 0.0% on an empty denominator. Grades produced by two DIFFERENT
    rubric versions are unmeasurable in a third way — the marks are all there and all ruled,
    and they answer different keys.

    @brief Classify a directory as unmeasurable and say why.
    @return Reason, or "" when the directory carries real coverage data.
    @version 2
    """
    if data is None:
        return "no such directory"
    checks = (
        (not data["cells"], "no *.grade.json sidecars — nothing has been graded here"),
        (not data["marks"], f"{data['cells']} sidecar(s) carrying zero marks"),
        (bool(_mixed_keys(data)), _mixed_keys(data)),
    )
    return next((why for failed, why in checks if failed), "")


## @brief Print the overall verdict and return the process exit code.
## @param dirty Count of cells still needing a re-grade.
## @param unmeasurable (path, reason) pairs for inputs that carry no coverage data.
## @return Exit code: 0 only when every graded cell is fully ruled AND there was data.
## @version 1
## @dg_internal
def _verdict(dirty: int, unmeasurable: list[tuple[Path, str]]) -> int:
    """@brief Render the gate's verdict.
    @return Exit code.
    @version 1
    """
    for root, reason in unmeasurable:
        print(f"\nERROR: {root}: {reason}")
    if unmeasurable:
        print(
            "\nUNMEASURED — coverage cannot be 'complete' over data that is not there, "
            "or that answers more than one grading key."
        )
        return 1
    ## NON-ZERO while any cell is short of a full ruling, so this can gate a claim. A score
    ## computed over partial coverage is not a weaker result, it is a different measurement.
    print(
        f"\n{'COMPLETE — every graded cell fully ruled' if not dirty else f'{dirty} cell(s) still need re-grading'}"
    )
    return 1 if dirty else 0


## @brief CLI entry point.
## @param argv Answers directories to check.
## @return Exit code.
## @version 1
def main(argv: list[str]) -> int:
    """Every input is inspected before anything is reported, so a missing directory names
    itself alongside the others instead of aborting the run on the first one.

    @brief Report grading coverage for each directory and gate on it.
    @return Exit code.
    @version 1
    """
    if not argv:
        print("usage: grading_coverage.py <answers-dir> [<answers-dir> ...]")
        return 2
    dirty = 0
    unmeasurable: list[tuple[Path, str]] = []
    for arg in argv:
        root = Path(arg).expanduser().resolve()
        data = coverage(root) if root.is_dir() else None
        reason = _unmeasurable(root, data)
        if reason or data is None:
            unmeasurable.append((root, reason))
            continue
        _report(root.name, data)
        dirty += data["degraded"]
    return _verdict(dirty, unmeasurable)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
