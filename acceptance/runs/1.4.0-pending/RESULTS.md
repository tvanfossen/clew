# 1.4.0 — results (SUPERSEDED)

**Superseded by `acceptance/runs/1.4.0-final/`.** This grid missed the gate on 2 of 4 repos; the
transcript review and the fixes it led to are recorded in `1.4.0-final/PRE-REGISTRATION.md` and
commit `c21b9176`.

Grid at `0dd5ba1b` (clean tree), per `PRE-REGISTRATION.md`: 4 targets × 3 arms × 3 replicates,
189 cells; answering `claude-haiku-5-5`, judge `claude-sonnet-4-5-20250929` k=3, grader
fingerprint `72a6c7bd363d`, seed 7. Index arms ran with the plugin's server environment
(`CLEW_WIRE=compact`). Comparator: `acceptance/runs/1.3.0-final/`.

> **Correction (2026-11-17).** The judge named above is wrong. Every grade of this run records `judge_model: claude-sonnet-5-5` (189/189) — the provider-canonical id adopted in 844fee55 and disclosed in the 1.2.0 pre-registration. `claude-sonnet-4-5-20250929` was text carried over from an earlier record. The figures are unaffected: they were measured with what the grades record. Found by the 2.0.0 rubric cross-check; `tests/test_run_records.py` now checks every run's record against its grades. The line above is left as published.


## Judge integrity

| pass | errored samples | rate | split decisions |
|---|---:|---:|---:|
| grid grading (a usage limit was reached mid-grade) | 1,991 / 3,888 | 51.21% | 690/1,296 (53.2%) |
| repair 1 (all four targets; the limit was reached again) | 265 / 3,888 | 6.82% | 145/1,296 (11.2%) |
| repair 2 (all four targets, after a confirmed reset) | **0 / 3,888** | **0.00%** | **56/1,296 (4.3%)** |

Method: `scripts/judge_error_rate.py acceptance/runs/1.4.0-pending`. A repair pass re-runs
`acceptance grade` per target; cached successful samples replay, only errored samples are re-judged.
The split rate falls with the error rate because an errored sample counts as a disagreement
(KNOWN-DEFECTS, 1.3.0). Final split rate is non-zero, so k=3 voting is live.

## Gate — per repo, index_only arm (pre-registered)

Method: `scripts/gate_figures.py` (committed in `c21b9176`). Total tokens = input + output + cache_read + cache_creation summed
over the repo's cells from each `.meta.json`, as % vs that repo's baseline arm in the same grid.
Separation = per-cluster (arm mean − baseline mean over replicates), averaged over the repo's
clusters; a cell with no ruled score is excluded. The script reproduces 1.3.0-final's published
per-repo figures exactly.

| repo | tokens 1.3.0 | tokens 1.4.0 | cost | separation 1.3.0 | separation 1.4.0 | quality (≥ 1.3.0 − 3.0) | gate |
|---|---:|---:|---|---:|---:|---|---|
| mattermost | +13.6% | +21.6% | **miss** | +1.37 | +3.89 | ok | **MISS** |
| mbedtls | −17.0% | −35.4% | ok | +2.55 | +7.29 | ok | PASS |
| self | −70.0% | −70.4% | ok | −5.92 | −11.67 | **miss** (floor −8.92) | **MISS** |
| entropic | −34.6% | −43.5% | ok | −7.01 | −5.97 | ok | PASS |

**The gate is NOT met: 2 of 4 repos miss** (mattermost on cost, self on quality).

## index arm (reported, not gated)

| repo | tokens 1.3.0 | tokens 1.4.0 | separation 1.3.0 | separation 1.4.0 |
|---|---:|---:|---:|---:|
| mattermost | +28.2% | +12.7% | +6.79 | +1.16 |
| mbedtls | +27.8% | +17.0% | +2.60 | +11.84 |
| self | −57.7% | −49.5% | −8.72 | −7.16 |
| entropic | +20.6% | −1.4% | −0.76 | −2.80 |

## Baseline drift (this grid's baseline vs 1.3.0-final's; never folded into a separation)

| repo | baseline score | baseline tokens |
|---|---:|---:|
| mattermost | +2.65 pt | +2.9% |
| mbedtls | −5.17 pt | +8.7% |
| self | +1.21 pt | −12.0% |
| entropic | −1.46 pt | +6.4% |

## Per-cluster separations (index_only / index), points

| repo | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 |
|---|---|---|---|---|---|---|
| mattermost | +2.22 / +8.89 | +3.33 / −6.67 | +5.56 / 0.00 | 0.00 / −4.76 | +8.33 / +8.33 | — |
| mbedtls | +23.33 / +28.33 | +6.06 / +11.11 | −27.59 / −3.45 | +1.33 / +5.33 | +33.33 / +17.86 | — |
| self | −4.17 / +2.08 | −34.92 / −17.46 | −9.88 / +7.41 | −25.29 / −25.29 | −3.70 / −4.94 | +7.94 / −4.76 |
| entropic | −17.46 / +4.76 | −5.13 / −15.38 | −7.78 / −12.22 | +2.47 / 0.00 | −1.96 / +8.82 | — |

Method: `scripts/gate_figures.py` (`clusters`). Per-cluster figures are 3
replicates per arm; between two 1.3.0 grids on an unchanged rubric, single clusters moved by up to
20 pt, so a single cluster is not evidence on its own.

## Not yet established

- why mattermost index_only cost rose (+13.6% → +21.6%) while its index arm fell (+28.2% → +12.7%);
- whether self's index_only miss (Q2 −34.9, Q4 −25.3) is the 1.3.9 docstring compaction
  (`compact_docs`, the one change that moved self dossiers by −12.7%) or replicate noise.

No release action is taken on these results without the owner's decision.
