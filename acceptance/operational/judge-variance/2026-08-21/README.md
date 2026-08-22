<!-- SPDX-License-Identifier: MIT -->
# Judge variance, 2026-08-21 — a frozen record

40 pairs x 3 reps, 120 calls. **0 flips, 0 transport errors.** Bounds the per-pair flip rate at
roughly **<=7.5% at 95% confidence** (rule of three). It does not show the rate is zero.

**NOT REGENERABLE, and the rows are in an obsolete shape.** These were measured against the
previous rubric generation, whose transcripts and grading sidecars were deleted in the 002
overhaul. The row keys (`mark_index`, `conceptual`) predate the current decision model, so
`scripts/judge_variance.py` no longer reads them — deliberately, rather than teaching the tool
two shapes and letting a reader mistake archived rows for current ones.

The measurement stands as a recorded result. To re-establish the bound on the current grader,
run the script against a fresh `generate` + `grade` pass; the number is a property of a judge,
not of the design, and the judge model can be repointed.

**One caveat that could not be measured away:** the judge was invoked as `--model sonnet`, an
alias. The current schema refuses an alias and requires a dated id, so a repeat is pinned in a
way this one was not.
