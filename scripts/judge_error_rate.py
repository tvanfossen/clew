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
@version 1
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
    print(f"cells graded      {cells}")
    print(f"judge samples     {samples}")
    print(f"errored           {errors}")
    print(f"rate              {rate:.2f}%  (threshold {args.threshold:.2f}%)")
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
