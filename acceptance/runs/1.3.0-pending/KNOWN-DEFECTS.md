<!-- SPDX-License-Identifier: MIT -->

# Known defects found by the 1.3.0 run

None is fixed in this run's numbers — the pre-registration forbids a grader change once numbers
exist. Each is recorded for the NEXT run.

## 1. The split rate counts a judge ERROR as a disagreement

`scripts/judge_error_rate.py` counts a voted decision as split when its `agreement` is below 1.0,
and an errored sample lowers agreement. Measured on the comparator re-grade: mbedtls, which had no
errors, read the same split count before and after repair (20/315); entropic read 76 → 30 and self
85 → 25 once their outage errors were repaired. During an outage the split rate therefore reports
judge failure as judge uncertainty. It is correct only when the error count is zero — which is
why both figures above are quoted after repair.

## 2. A grid's grading does not fit one usage window

Generation and judging run through the same account; ~3,900 k=3 judge samples outran the window
twice. Grading must be planned as separate passes started after a reset, with repair passes, or
the instrument should move judging to its own quota.

## 3. Wall-time figures are not reproducible from the method in use

The token reductions here reproduce 1.2.0's published −38.2% / −53.4% exactly by summing cells.
1.2.0's published wall figure (−41.7%) does not reproduce that way (−37.7%), so its method is
unrecorded. Wall time is omitted from this run's headline for that reason.

## 4. Judge calls persist a CLI session each (found 2026-11-04)

Every `claude -p` judge call is saved as a session transcript under
`~/.claude/projects/<cwd slug>/`; nothing reads them, since verdicts are cached in each run's
`judge-cache`. 48,412 had accumulated (14.9 GB) and filled the machine's disk. The fix is
`--no-session-persistence` on the judge's argv, but `acceptance/grader/` is frozen at the
pre-registered fingerprint `72a6c7bd363d` for this grid, and the fingerprint hashes the grader's
source. Until the next release unfreezes it, run `scripts/prune_judge_sessions.py` after each
grading pass.
