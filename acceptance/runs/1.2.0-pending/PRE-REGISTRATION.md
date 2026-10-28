<!-- SPDX-License-Identifier: MIT -->
# Pre-registration — 1.2.0, written before any cell was generated

**Committed as its own act, before the grid runs.** Every number this directory later holds is
to be read against the criteria below, whichever way they land.

## The reason this file is more necessary than 1.1.0's, not less

1.1.0's pre-registration opened by confessing that the instrument had been changed twice after
an unfavourable result, and named the pattern: *measure → dislike the result → adjust the
instrument is how a benchmark becomes a self-portrait.*

Since that run, more has changed than changed before it, and **the changes were found by
reading the clusters where clew lost.** That is the same shape. Stating it plainly:

| what changed | from → to |
|---|---|
| `grader_fingerprint` | `9cc2b15baf93` → `5489758d9a50`, four moves |
| `rubric_digest`, mbedtls | `43aae606077ca386` → `df99c485d2299d92` |
| `rubric_digest`, entropic | `9c6dc8800d760d1e` → `45ccebd5581c068a` |
| `rubric_digest`, self | `47cdb1e6a8e6c4bb` → `e8bcc09226dcf43d` |
| tool code paths | 16 |

**The grader change moved a published number in clew's favour, and that is the one to distrust
most.** `QuestionResult.score` returned `0.0` for a question the judge ruled *nothing* on; three
`self` Q6 blended cells had 18 of 18 judge calls error and were scored zero. Excluding only
cells where nothing was ruled, `self`'s blended arm reads 45.4 rather than 37.9 — a 6.1-point
loss becomes a 1.4-point win — and the blended headline reads +1.54 rather than +0.25.

That correction is defensible: a question nothing was ruled on is unmeasured, and publishing it
as zero is absence reported as a measurement. It is also, unavoidably, a grader edit that
flatters the tool, made by the party it flatters. It is disclosed here rather than discovered
later, and the 1.2.0 criteria below are fixed before the numbers exist precisely because that
disclosure is not by itself a defence.

**The rubric digests moved for one reason**, recorded when it was done:
`samples_when_weight_at_least` went 2 → 1, so every mark is now judged three times instead of
single-sampled. No mark text, weight, `refs` or question was edited. That is checkable against
`git log acceptance/targets/`, and a reader who does not trust this sentence should check it.

## What is pinned

| | |
|---|---|
| targets | mbedtls, entropic, self — **unchanged from 1.1.0** |
| questions | 16 (5 + 5 + 6), 136 marks, 318 weight |
| arms | `baseline`, `index_only`, `index` |
| replicates | 3 → 144 cells |
| answering model | `claude-haiku-5-5` |
| judge | `claude-sonnet-4-5-20250929` |
| `grader_fingerprint` | `5489758d9a50` |
| seed | 7 |

No target is added and none is removed. riot stays out for the reason 1.1.0 gave — a
provisioning failure is not a score of zero — and the three authored-but-unrun targets stay out
so that this run is comparable to the last on the one axis that matters.

## The criteria, fixed now

### 1. Quality — the primary claim

**The `index_only` arm's mean per-cluster separation from `baseline` improves on −13.92 pt by
more than the measured noise floor.**

The floor is measured on this grid, not carried over: `grade` runs at least twice over the
identical frozen answers at one `(rubric_digest, grader_fingerprint)` pair, and the floor is the
observed pass-to-pass spread. A movement inside the floor is **unresolved** — not a win, not a
loss. The 1.1.0 floor was 8.95 pt mean absolute over 21 re-graded cells; if this run's floor
lands near that, a movement under ~6.6 pt cannot be claimed either way, and that is the expected
outcome rather than a surprise.

**Pre-registered expectation: +3 pt, which is BELOW that floor.** This is written down so the
likely result — "moved in the right direction, unresolved" — is recorded in advance as the
expected one, and cannot later be presented as either a disappointment or a win.

### 2. Retrieval — the secondary claim, and the one with evidence behind it

**The share of `dossier` calls returning nothing falls from 26.7%.** Counted from transcripts by
`scripts/selector_waste.py`, zero judge calls.

Evidence already in hand, and stated so it can be checked against the run rather than taken on
trust: replaying the 1.1.0 agents' own calls against the same frozen indexes with current code,
67 of 85 previously-empty calls now answer (78.8%); on five freshly generated mbedtls cells the
missed-subject rate was 0 of 67.

**This is not the hypothesis.** A call that answers is necessary for a better answer and does
not constitute one. If quality is unresolved and retrieval improves, the honest report is
exactly that, and it is written here so it cannot be dressed up.

### 3. Cost

**`output_tokens` and `cache_read_tokens` are reported separately and never summed.**
`cache_read` is 98% of tokens spent and was −39.2% on the 1.1.0 grid against −35.2% for output;
quoting only output understates the axis. No cost claim is made against 1.1.0 for the reason
that run already recorded: the index arms receive ~5,560 characters of MCP instruction text the
baseline does not, and that confound is unresolved.

### 4. Judge error rate — new, and it is a publication gate

**If more than 2% of judge samples error, the run is reported as degraded and the quality figure
is withheld.**

1.1.0 spent 2,970 judge samples and 152 of them — 5.1% — errored, across 14 cells, with 4 cells
100% unruled and scored 0.0 anyway. Nothing surfaced it. The report now prints `unruled` rather
than absorbing it into a zero, and this threshold exists so a repeat is a stop rather than a
footnote.

## What would falsify the work

- quality moves *against* clew outside the floor → published with its sign, and the retrieval
  fixes did not buy what they were built for
- retrieval improves and quality does not move → the ceiling is answer construction, not
  reachability, and the next release targets that instead
- judge error rate above 2% → no quality figure from this run at all

## What this run may not do afterwards

No rubric edit, no mark reweighting, no question exclusion, and no grader change after the
numbers exist. A defect found in the grader *by* this run is recorded and fixed for the NEXT
run; it does not re-score this one. The frozen 1.1.0 cells are not re-graded to match — they are
published evidence at their own fingerprint, and `RESULTS.md` there already carries the
correction note rather than edited figures.
