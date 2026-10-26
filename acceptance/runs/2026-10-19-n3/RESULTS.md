<!-- SPDX-License-Identifier: MIT -->
# clew 1.1.0 — acceptance baseline

**First measurement against `docs/CORE_HYPOTHESIS.md`. The hypothesis is NOT supported in its
strong form.** This is a target to improve against, not a result to defend.

Read `KNOWN-DEFECTS.md` beside this file before quoting any number from it. Fourteen defects are
disclosed there, each with the direction it moves the figures.

---

## The result

| | baseline<br>(shell, no index) | `index_only`<br>(index, no shell) | `index`<br>(both — the shipped shape) |
|---|---:|---:|---:|
| **completeness** | 58.1% | **44.2%** | 58.4% |
| vs baseline | — | **−13.92 pt** | +0.26 pt |
| output tokens | 6,030 | **−35.2%** | −15.4% |
| cache-read | 356,836 | **−39.2%** | −12.8% |
| cache-creation | — | −14.0% | — |
| cost | — | −25.4% | — |
| wall seconds | 35 | **−27.7%** | −12.5% |
| turns | 11 | −2.4% | +0.2% |
| tool calls | 10 | −2.7% | +0.2% |
| shell calls | 10 | **−100%** | −39.8% |

144 cells · 3 repositories · 48 pairs in **16 (target, question) clusters** · answering model
`claude-haiku-5-5` · judge `claude-sonnet-4-5-20250929` · seed 7 · n=3 replicates.

**Statistics.** Cluster-robust **SEM 3.31 pt → 4.2σ**. The naive n=48 figure (2.45 pt, 5.7σ)
overstates precision because three replicates share a question and are tightly correlated —
`mbedtls` Q4 is −40.0 pt in all three with byte-identical hit patterns in both arms. Target-level
clustering (3 clusters) gives 3.58 pt, 3.9σ. The cluster-robust figure is the published one.

**Judge noise.** 21 cells re-graded against the identical rubric digest and grader fingerprint:
mean absolute pass-to-pass spread **8.95 pt**, median 7.69, max 30.0, signed mean +1.56 pt — so
the judge is unbiased and high-variance. The subset is deliberately mid-range (`scripts/floor_subset.py`),
which **overstates** the run-wide floor; for a published loss that bias argues against the claim.

**No per-question figure is reported.** With n=3 per question and a per-cell floor of ±8.95 pt,
nothing at question granularity is worth printing — including figures from this run quoted
elsewhere during development.

**No parity claim.** `PRE-REGISTRATION.md` defines parity against a floor measured by grading all
144 answers twice. That pass never ran. A 13.92 pt loss is a difference, not a parity test.

---

## What this does and does not establish

The hypothesis is *"the index yields better answers more cheaply."* The halves came out
differently, and collapsing them would misreport both.

**"Better answers" — contradicted, resolved.** The index alone is 13.92 pt less complete than a
shell-only agent at 4.2σ. That is a measured negative, not an open question, and it holds under
every exclusion tried: dropping the two contaminated questions gives −11.16; dropping `self`
entirely −17.93; dropping saturated and never-reached decisions −24.50. Range −11.2 to −24.5, all
negative, the published figure near the conservative end.

**"More cheaply" — good early numbers, PROVISIONAL.** −35.2% output tokens is real arithmetic but
confounded: the index arms receive roughly 1,900 characters of `INSTRUCTIONS` plus three tool
descriptions in their system prompt, and a 299-character brief against baseline's 67, all of it
pushing toward fewer, larger calls — *precisely the axis this measures*. `check_symmetry` guards
only the brief. The sensitivity is already demonstrated: `runs/2026-10-20-skills-ab` moved
entropic's separation by adding a usage document to the same surface. The figures are also ratios
of means; means of per-pair ratios are −32.5% / −31.6% / −23.4%.

`PRE-REGISTRATION.md` limitation 6 independently requires the provisional label: zephyr is the
scale test and has not landed, so the grid is incomplete as a cost result by its own terms.

**The shipped configuration is quality-neutral and cheaper.** The blended arm scores +0.26 pt
against baseline at −15.4% output tokens. Per the owner ruling of 2026-10-18 and Amendment 1,
blended figures measure ADOPTION — one model's willingness to stop grepping — and are reported as
operational context, never as a property of the index.

## Why the index loses, where it loses

Eleven decisions are hit 3/3 by baseline and 0/3 by `index_only`. Four causes, and only one is
reachable by better retrieval:

| cause | decisions | fixable by indexing more? |
|---|---:|---|
| files outside the indexed set — `scripts/generate_errors.pl` has **zero** index rows; Perl is not among the 21 grammars | 4 | **no** |
| negative space — a default that FAILS, a default-ALLOW posture | 2 | **no** |
| tree-wide aggregation the index already holds the rows for | 3 | **yes** |
| threads whose lambda has no named entry | 1 | **no** |

It wins the mirror image: precise, symbol-local facts (`MBEDTLS_CT_ASM is DERIVED rather than
configured`; `the asm path is an empty asm volatile`).

**The clearest single improvement found** is not retrieval at all. Tracing one cell by hand:
`dossier('execute')` returns a definitive negative advising a check of `target` and staleness,
neither of which was the problem — the symbol is `ServerManager::execute`. The agent asked for the
bare name four times, having already called the qualified form successfully. A near-miss
suggestion would have ended a four-call loop immediately. Five of that cell's sixteen calls, 31%,
went to that and to passing file paths to a symbol tool.

## Reproducing this

Pinned: target commits (verified by `check_revision`, including a dirty-tree check), rubric
digests recorded in every sidecar and matching the on-disk rubrics, `grader_fingerprint` uniform
across all 144 cells and the floor pass, judge model by dated id, seed, and clew's own identity —
version, commit, dirty flag, build version and the substrate's compiled-in language set — in both
`run.json` and `provision.json`.

**Not reproducible, and these are the gaps to close before the next baseline:**

1. **The answering model is an alias.** `claude-haiku-5-5`, not a dated snapshot, while
   `grader/rubric.py` *refuses* an alias for the judge. We enforce for the grader what we do not
   enforce for the subject. A third party cannot reproduce the arms.
2. **`run.json` lost its per-window provenance.** A no-op `generate --resume` rewrote all three
   after the answers were frozen, so `resumed` now lists every cell and no longer says which
   window produced what.

### Added 2026-10-26: this run's grading keys are now historical

Both keys this run was graded under have since moved, deliberately, and **these cells can no
longer be re-graded at their own keys from the current tree.** They remain re-gradable from the
tagged tree that produced them, which is where a third party reproducing this must start.

| key | here | now | why it moved |
|---|---|---|---|
| `grader_fingerprint` | `9cc2b15baf93` | `274b0d72688b` | a verdict cache was added to `judge.ask` |
| `rubric_digest` (all targets) | as recorded per sidecar | changed | `samples_when_weight_at_least` 2 → 1 |

**Both changes answer a defect this run disclosed rather than adding a feature.** Gap 1 above was
closed by replacing the dated-id requirement with a canonical-id requirement plus recorded
provenance — the provider publishes no dated form for the current family, and
`modelUsage.canonicalModel` in all 144 transcripts here is *also* `claude-haiku-5-5`, so there was
never a dated id to record. Gap 2 was closed by appending one window record per `generate`.

The judge-noise finding at the top of this file — **8.95 pt mean absolute spread** over 21
re-graded cells — drove both of the key changes:

- The CLI the judge runs through exposes no temperature, seed or top_p, so every call is a sample
  at default sampling. A verdict cache keyed on prompt and model makes a re-grade exact and free.
  Calling the API directly to pin temperature would have moved roughly 3.1M judge input tokens per
  pass onto metered billing, recurring forever, and still left residual nondeterminism.
- **12.7% of this run's graded weight was decided by a single judge call**, because marks of
  weight 1 were not voted. Every mark is now voted at k=3, for +10% judge calls. That share is
  now 0%.

Neither correction changes a number on this page. They change what the NEXT baseline can claim,
and they mean this one's figures carry a wider interval than its own `±3.31 pt` cluster SEM
suggests — a per-question swing of ±10 pt was free on this instrument.

## What to beat

Next baseline should improve on: **−13.92 pt completeness** at **−35.2% output tokens**, with the
cost axis de-confounded so the saving is attributable to retrieval rather than to coaching. The
three fixable items above — tree-wide aggregation, the near-miss hint, and the unnamed-lambda
thread gap — are the measurable work.
