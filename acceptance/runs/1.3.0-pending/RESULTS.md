<!-- SPDX-License-Identifier: MIT -->

# clew 1.3.0 acceptance — results

Measured 2026-11-02/03 at `2697f35`. Criteria fixed in `PRE-REGISTRATION.md` (and its dated
addendum) **before** any cell was generated; read those first.

## The headline: the pre-registered gate was NOT met, and 1.3.0 is not tagged

| figure | 1.3.0 | comparator (1.2.0 answers re-graded at `72a6c7bd363d`) | delta |
|---|---:|---:|---:|
| **held 16, `index_only` separation** — the gate | **−0.38 pt** | −0.05 pt | −0.33 |
| held 16, `index` separation | +2.23 pt | +2.52 pt | −0.29 |
| full grid (21 clusters) `index_only` / `index` | −2.73 / +1.54 pt | — | not a delta |
| **mattermost, first baseline** `index_only` / `index` | **−10.26 / −0.64 pt** | — | none exists |
| baseline drift — mean baseline score, held 16 | 50.94 | 50.48 | +0.46 |

Separation is each arm's mean score minus the baseline arm's, per `(target, question)` cluster,
averaged over clusters. The method was validated by reproducing 1.2.0's published −1.58 / +1.56
exactly from 1.2.0's own sidecars before it was applied here.

**Decision B, path by path:**

- *quality improves without cost shifting*: **fails** — −0.38 is below the comparator's −0.05.
- *cost improves without quality shifting*: quality is within 1 pt (−0.33) but **fails** on cost —
  neither axis improved on 1.2.0.

| `index_only` vs baseline, held 16 (sums over cells) | 1.2.0 | 1.3.0 |
|---|---:|---:|
| output tokens | −38.2% | −33.3% |
| cache-read tokens | −53.4% | −50.8% |

Both are within Decision B's 5-point "does not shift" tolerance; neither is a >5-point improvement.

**Owner's ruling, 2026-11-03: do not ship; improve, at minimum, the TypeScript result.**

## What the numbers can and cannot say

**THE HELD-16 MISS IS INSIDE THE SPREAD.** Per-cluster deltas against the comparator run from
−31.25 (self Q1) to +28.21 (entropic Q2) at three replicates, and no noise floor is measured on a
one-pass grid. The 1- and 5-point margins are DECLARED TOLERANCES, not statistical thresholds. So
"not met" is the reading, not "measurably worse" — and equally not "unchanged".

**THE TYPESCRIPT RESULT IS A REAL DEFICIT.** On mattermost-mobile `index_only` answers scored
10.3 pt below the shell-only baseline (Q4 −21.4, Q5 −18.8) while reading **32.6% more**
cache-read tokens. On this target the index-only agent was both less complete and more expensive.

**The voting repair, measured.** Re-grading 1.2.0's frozen answers with genuine k=3 voting moved
its published figures from −1.58 → −0.05 (`index_only`) and +1.56 → +2.52 (`index`). That is the
size of the grader fix `891b73d`, and it is why the comparator is the re-grade, not the published
number (Decision A).

## Instrument health

| | |
|---|---|
| judge errors | **0 of 3,888** samples (after repair — below) |
| split decisions | 61 of 1,296 voted (4.7%) — non-zero, so k=3 voting took effect |
| comparator judge errors | 0 of 3,294 (after one repair) |

**TWO USAGE-LIMIT OUTAGES, REPAIRED AND DISCLOSED.** Grading shares the account the agents run on.
A limit hit during mbedtls and self grading: errors 1,725 of 3,888 (44%). Two repair passes, each
started after a confirmed recovery, re-asked ONLY the errored samples — errors are never cached,
successes are, so every verdict ruled in the first pass replayed unchanged. entropic and
mattermost were graded clean in the first pass. The comparator re-grade had the same kind of
repair. No sample was re-asked that had already been ruled.

**A superseded grid exists**, at `f9e98a5`, unanalysed; why is in the pre-registration addendum.

## What produced these numbers

| | |
|---|---|
| clew | `2697f35`, clean, build version 9, `clew_version` 1.3.0 |
| targets | mbedtls `068ff080b369`, entropic `6dcb4c814639`, self `a6dd8ed919e6`, mattermost `4d842026f691` |
| cells | 189 (144 held + 45 mattermost), every arm regenerated |
| answering model / judge | `claude-haiku-5-5` / `claude-sonnet-5-5`, both floating |
| `grader_fingerprint` | `72a6c7bd363d` |
| generation cost | $2.52 for all 189 cells |

Known defects in this instrument: `KNOWN-DEFECTS.md`.
