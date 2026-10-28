<!-- SPDX-License-Identifier: MIT -->

# clew 1.2.0 acceptance — results

Measured 2026-10-28. Criteria fixed in `PRE-REGISTRATION.md` **before** any cell was generated;
read that first, including the parts that say what this run cannot claim.

## The headline

`index_only` reaches **parity on quality** while cutting tokens and wall time by roughly half.

| H₁ axis | 1.1.0 | **1.2.0** | delta |
|---|---:|---:|---:|
| **quality** — `index_only` separation | −13.92 pt | **−1.58 pt** | **+12.34** |
| **tokens** — output | −35.2% | **−38.2%** | +3.0 |
| **tokens** — cache_read | −39.2% | **−53.4%** | +14.2 |
| **time** — wall | −30.8% | **−41.7%** | +10.9 |

Blended (`index`), the arm that keeps shell access:

| H₁ axis | 1.1.0 | **1.2.0** |
|---|---:|---:|
| quality | +0.25 pt | **+1.56 pt** |
| output | −15.4% | −14.2% |
| cache_read | −12.8% | −11.7% |
| wall | −15.3% | **−21.4%** |

Negative is cheaper or faster; positive quality is better than the shell-only baseline.

## THE NUMBER IS NOT ATTRIBUTABLE TO clew ALONE, AND THIS IS THE FIRST THING TO READ

The grader changed between the two runs. `5b14197` found `_key` dropped a trailing `:LINE`, so
an answer citing `path:line` could not match the member it named — one cell lost 18.5 points.
That bug was **deterministic** and **asymmetric**: it punished whichever arm cites line numbers,
which is the citation style a code index encourages. Its own commit says every quality figure
measured before it is void.

So part of +12.34 is the instrument no longer penalising the arm under test, and **this run
cannot say how much.** Isolating it would need a different-family judge and a held grader; that
is 1.3.0. The owner's ruling of 2026-10-28 was to disclose rather than re-grade 1.1.0 — a
different version of the tool — and that is what this page does.

## Per cluster, 16 of them

```
cluster           io 1.1.0  io 1.2.0    delta |  blended 1.1.0   1.2.0
mbedtls Q4          -40.00    +17.33   +57.33 |      -4.00      -6.67
self Q3             -22.22    +11.11   +33.33 |     -14.81     +14.81
self Q1              -8.33    +18.75   +27.08 |      +2.08     +12.50
mbedtls Q5          -16.67     +8.33   +25.00 |      +9.52     +22.62
mbedtls Q3          -26.44     -6.90   +19.54 |      +3.45     +10.34
self Q6             -11.11     +7.94   +19.05 |     -19.05      +4.76
mbedtls Q1           +8.33    +26.67   +18.33 |     +15.00     +25.00
entropic Q5         -25.49     -7.84   +17.65 |      +5.88      -4.90
mbedtls Q2          -12.12     +3.03   +15.15 |      +4.04      +5.05
entropic Q3         -21.11     -6.67   +14.44 |      -4.44      -2.22
entropic Q1         -17.46     -4.76   +12.70 |      -3.17      -1.59
entropic Q4         -28.40    -19.75    +8.64 |      -8.64      -4.94
self Q5              +4.94     -8.64   -13.58 |      +6.17       0.00
self Q4              -3.45    -19.54   -16.09 |       0.00     -26.44
entropic Q2          +0.00    -20.51   -20.51 |     +23.08      +5.13
self Q2              -3.17    -23.81   -20.63 |     -11.11     -28.57
```

**12 of 16 improved. 7 are now positive** against 3 in 1.1.0. Four regressed, and they are named
above rather than averaged away: self Q2, entropic Q2, self Q4, self Q5.

**mbedtls Q4 moved +57.33**, from the worst cluster in the grid to +17.33. It is the generated-file
provenance question: `dossier("library/error.c")` now returns the rule that generates it, naming
`scripts/generate_errors.pl` and `library/CMakeLists.txt:134`. Before the fix, 9 of 21 points of
failed weight were reachable; after it, 21 of 21.

Per target, `index_only`: mbedtls **+9.69**, self −2.37, entropic −11.91.

## Dispersion, and what it is NOT

| | index_only | blended |
|---|---:|---:|
| mean of 16 cluster gaps | −1.58 | +1.56 |
| standard deviation | 15.49 | 14.77 |
| SEM | 3.87 | 3.69 |

**This is cluster-to-cluster variation, NOT judge variance.** It describes how differently the
index performs across questions, not how much the measurement would move on a re-run. No noise
floor was measured — that needs a second grading pass with `--no-judge-cache`, and the ruling was
one pass. 1.1.0's 8.95 pt floor is **not** reused: it was measured through the buggy grader and
describes a different instrument.

## Criterion 4 — the publication gate, passed

| | 1.1.0 | 1.2.0 |
|---|---:|---:|
| judge samples | 2,970 | 3,294 |
| errored | 152 | **0** |
| rate | 5.12% | **0.00%** |

Below the 2% threshold, so the quality figure above is published rather than withheld. Reproduce
with `.venv/bin/python scripts/judge_error_rate.py acceptance/runs/1.2.0-pending --threshold 2`.

## Two defects this run found in its own instrument

Neither is fixed in these numbers. `PRE-REGISTRATION.md` forbids a grader change once numbers
exist; both are recorded here and fixed for the NEXT run.

**1. k=3 VOTING IS NULLIFIED BY THE VERDICT CACHE.** `judge.py:570` computes the prompt ONCE
outside the sample loop and calls `ask(prompt, model)` three times. The cache keys on
`sha256(model + prompt)`, so samples 2 and 3 replay sample 1. Evidence: **1,239 distinct cache
entries for 3,294 recorded samples**, and a split rate of **0 of 1,098 voted decisions** where
1.1.0 — graded before the cache existed — split 15.6%.

Both halves shipped in the same commit. `5b14197` raised k to 3 on every mark *because* 12.7% of
the grid's weight was decided by a single judge call, and added the cache that collapses it back
to one. The verdicts in this run are valid single samples; they are **not voted**, and the
pre-registered split-rate comparison is void — it measures nothing here.

**2. A `None` score crashed the grading phase.** `QuestionResult.score()` returns `float | None`,
where None means nothing was ruled — the change that stopped an unruled question publishing as a
confident 0.0. The progress line still formatted it with `:6.1%`, so the first fully-unruled cell
killed `self`'s grading after 90 cells. The sidecar is written *before* that line, so no score was
lost or altered. Fixed in `acceptance/__main__.py`, which is outside the fingerprinted directory —
`grader_fingerprint` was verified unmoved at `5489758d9a50` after the fix.

## What produced these numbers

| | |
|---|---|
| targets | mbedtls `068ff080b369`, entropic `6dcb4c814639`, self `a6dd8ed919e6` |
| questions / marks / weight | 16 / 136 / 318 |
| arms | `baseline`, `index_only`, `index`, rotated per replicate |
| replicates | 3 → 144 cells |
| answering model | `claude-haiku-5-5` — **floats**, no dated id exists |
| judge | `claude-sonnet-5-5` — **floats**; not the answering model |
| `grader_fingerprint` | `5489758d9a50` |
| rubric digests | mbedtls `bbf6195f605be452`, entropic `705c131e354e5c22`, self `d8447c7b18eafbf5` |
| seed | 7 |
| clew | 1.1.3 at commit `844fee55`, **`clew_dirty: true`** |

**THE TREE WAS DIRTY AND THE SHA ALONE DOES NOT PIN THE CODE.** The grid resumed carrying the
uncommitted `_grade_line` fix described above. That change is confined to
`acceptance/__main__.py`'s progress line, it is outside `acceptance/grader/`, and the fingerprint
was verified unchanged — but a reader resolving `844fee55` will not get the exact tree that ran,
and saying so is cheaper than letting them discover it.

**Both model ids float.** No dated form exists for the current families (`modelpin.py` documents
why at length), so a replay months from now may not answer or judge from the same weights.

## Reproducing

```bash
.venv/bin/python -m acceptance.matrix \
    --out acceptance/runs/1.2.0-pending \
    --only mbedtls entropic self \
    --models claude-haiku-5-5 \
    --replicates 3 --seed 7 --jobs 4 --resume
```

Grading replays exactly from the committed `judge-cache`, so a third party re-grading these
frozen answers gets these scores and not a re-sample.
