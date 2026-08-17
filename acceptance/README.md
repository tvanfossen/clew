<!-- SPDX-License-Identifier: MIT -->
# Acceptance evidence

**A rubric belongs to a TARGET. A result belongs to a target at a VERSION.**

```
targets/<target>/questions.md             the frozen rubric — ONE per target, versioned in its
                                          own front matter and in git history
targets/<target>/<version>/result.md      what that version measured — or FAILED.md if void
targets/<target>/<version>/run-n3/        every cell: answer, argv, raw payload, transcript,
                                          rendered history, per-mark grade
method/                                   target-independent: methodology, criteria, evidence
                                          guide, result template
```

**Why the rubric is per target and not per run.** Its marks cite that repository's ground truth —
symbols, `file:line`, measured counts — so it is a property of the target, not of a release. One
copy also means it cannot drift: duplicating it per version would create several files claiming to
be the same grading key, and nothing would reconcile them.

Cross-version comparison still needs to know whether the key moved, and it does: the rubric
carries a semantic version in its own front matter, and `git log` on the single file gives the
full change history. That is strictly better than comparing copies — a version bump in the front
matter is a claim a reviewer can check against the diff.

**Why the result is per version.** The measured effect differs sharply between targets and will
differ between releases. A layout that invited a blended number across either axis was actively
misleading — one target improves at every model tier while another's index was incomplete and its
run is void.

## Runs to date

| target | version | rubric | graded | outcome |
|---|---|---|---|---|
| [entropic](https://github.com/tvanfossen/entropic) — C++ | **0.5.0** | v2.0.0, 98 marks | **yes** — 198/198 cells, 1,665 marks, `unmarked_pct` 0.0% | [`result.md`](targets/entropic/0.5.0/result.md) |
| [mbedtls](https://github.com/Mbed-TLS/mbedtls) — C | **0.5.0** | v1.1.0, 83 marks | **no** | **[`FAILED.md`](targets/mbedtls/0.5.0/FAILED.md)** — void; the index did not contain the codebase |
| this repo — Python | 0.5.0 | drafted | no | self-index, kept for dogfooding |

**The mbedtls run is void, not weak.** Its index yielded **10** function bodies across 108 library
source files where a non-preprocessing parse finds **2,507**, because that code sits behind feature
macros the doxygen parse did not define. That arm queried the library's headers.

It is kept for two reasons: the failure is only legible next to entropic's clean run at the same
version and on the same harness, and it is the reproduction case for the issues that govern it —
[gh#6](https://github.com/tvanfossen/clew/issues/6),
[gh#11](https://github.com/tvanfossen/clew/issues/11). Deleting a failed run makes it read
as a run that never happened.

## Adding a run

A new run gets a new `<version>` directory; existing ones are never edited. The rubric is copied
in, not linked. When a fix lands, the re-run's value comes precisely from being comparable to the
directory it supersedes — **including a void one**.

## Reading any of it

[`method/EVIDENCE.md`](method/EVIDENCE.md) describes each artifact, its trust level, and a
one-minute procedure for spot-checking a single cell.
[`method/REDACTIONS.md`](method/REDACTIONS.md) records the four raw transcripts removed before
publication and what survives for those cells.
[`method/success-criteria.md`](method/success-criteria.md) states the bar a run is judged against;
[`method/methodology.md`](method/methodology.md) states how a cell is run and fenced.

Verify coverage before believing any score:

```
.venv/bin/python acceptance/bench/grading_coverage.py acceptance/targets/entropic/0.5.0/run-n3
```

It must print `unmarked_pct: 0.0%`. An unruled mark weighs exactly what a mark the judge ruled
MISS weighs, so a grading pass interrupted by session capacity produces a plausible-looking score
built from a fraction of its marks. That has happened twice here — 102 of 324 marks on one run, 449
of 1,026 on another — and neither was visible in the score itself.
