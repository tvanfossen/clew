# SPDX-License-Identifier: MIT
"""The share of judge calls that errored, over a graded run.

WHY A SCRIPT. 1.1.0 errored 152 of 2,970 judge samples — 5.1%, across 14 cells, four of them
scored 0.0 while 100% unruled — and nothing surfaced it. The number was recoverable from the
sidecars the whole time; no command computed it, so no reader saw it. A rate that exists only
as an arithmetic possibility is not a measurement.

IT IS A PUBLICATION GATE, not a diagnostic. `PRE-REGISTRATION.md` for the 1.2.0 run withholds
the quality figure above 2%, so this has to be runnable by someone who did not write it and has
to report the denominator alongside the rate — "5.1%" over an unstated number of samples is the
kind of figure this project removes rather than re-derives.

A CELL WITH NO SIDECAR IS UNREAD, NOT CLEAN. Counting it as zero errors would make an ungraded
grid the healthiest-looking one, so unreadable sidecars are reported separately and never folded
into the rate.

@brief Judge error rate over a graded run.
@version 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


## @brief One run's error tally, read from its grade sidecars.
## @param root Run directory holding one subdirectory per target.
## @return (samples, errors, cells read, unreadable paths).
## @version 1
def tally(root: Path) -> tuple[int, int, int, list[Path]]:
    """@brief Sum samples and errors over every decision.
    @return Samples, errors, cells, unreadable.
    @version 1
    """
    samples = errors = cells = 0
    unreadable: list[Path] = []
    for path in sorted(root.glob("*/answers/*.grade.json")):
        try:
            record = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            unreadable.append(path)
            continue
        cells += 1
        for decision in record.get("decisions", []):
            samples += int(decision.get("samples", 0))
            errors += int(decision.get("errors", 0))
    return samples, errors, cells, unreadable


## @brief How many voted decisions had their samples disagree.
## @param root Run directory holding one subdirectory per target.
## @return (voted decisions, split decisions).
## @version 1
def splits(root: Path) -> tuple[int, int]:
    """THE ONE NOISE INDICATOR A SINGLE GRADING PASS CAN GIVE. A floor needs two passes over
    identical answers; the 1.2.0 run has one, and it changed the judge from
    `claude-sonnet-4-5-20250929` to `claude-haiku-5-5`. Whether the cheaper judge disagrees with
    ITSELF more often is visible without a second pass: on the Sonnet-graded 1.1.0 grid, 146 of
    936 voted decisions split, 15.6%.

    VOTED DECISIONS ONLY. A single-sample decision cannot split, so including it would dilute
    the rate by however many marks the rubric left unvoted — turning a fact about the judge into
    a fact about the weights.

    IT IS NOT A NOISE FLOOR and must not be reported as one. It measures within-call-set
    disagreement on one pass, not pass-to-pass movement in the score.

    @brief Voted and split decision counts.
    @return Voted, split.
    @version 1
    """
    voted = split = 0
    for path in sorted(root.glob("*/answers/*.grade.json")):
        try:
            record = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for decision in record.get("decisions", []):
            if int(decision.get("samples", 0)) <= 1:
                continue
            voted += 1
            agreement = decision.get("agreement")
            if agreement is not None and float(agreement) < 1.0:
                split += 1
    return voted, split


## @brief Print the rate and its denominator.
## @return Exit code — 1 when the rate exceeds the threshold.
## @version 1
def main() -> int:
    """THE THRESHOLD IS AN ARGUMENT WITH A DEFAULT, not a constant, because the 2% in the 1.2.0
    pre-registration is that run's declaration rather than a property of grading.

    @brief Report the judge error rate.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(prog="judge_error_rate", description=__doc__)
    parser.add_argument("run", type=Path, help="a run directory, e.g. acceptance/runs/<name>")
    parser.add_argument("--threshold", type=float, default=2.0, help="percent that fails the run")
    args = parser.parse_args()

    samples, errors, cells, unreadable = tally(args.run)
    if not cells:
        print(f"REFUSED — no grade sidecars under {args.run}", file=sys.stderr)
        return 2
    rate = 100.0 * errors / samples if samples else 0.0
    voted, split = splits(args.run)
    print(f"cells graded      {cells}")
    print(f"judge samples     {samples}")
    print(f"errored           {errors}")
    print(f"rate              {rate:.2f}%  (threshold {args.threshold:.2f}%)")
    ## PRINTED BESIDE THE ERROR RATE because they answer different questions about the same
    ## instrument: how often it failed to answer, and how often it disagreed with itself. The
    ## Sonnet-graded comparison figure is quoted so the number means something to a reader who
    ## has only this output. NOT a noise floor — see `splits`.
    if voted:
        print(
            f"split decisions   {split}/{voted} voted  {100.0 * split / voted:.1f}% "
            f"(1.1.0 under claude-sonnet-4-5-20250929: 146/936, 15.6%)"
        )
    ## REPORTED, NEVER ABSORBED. An unreadable sidecar is a cell nobody graded, and folding it in
    ## as zero errors would make an empty grid the cleanest one on this measure.
    if unreadable:
        print(f"UNREADABLE        {len(unreadable)} sidecar(s), excluded from the rate")
        for path in unreadable:
            print(f"  {path}")
    if rate > args.threshold:
        print("DEGRADED — above threshold; the quality figure is withheld")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
