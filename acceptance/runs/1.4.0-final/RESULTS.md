# 1.4.0-final — results

Grid at `4a0998d7` (clean tree), per `PRE-REGISTRATION.md`: 4 targets × 3 arms × 3 replicates,
189 cells; answering `claude-haiku-5-5`, judge `claude-sonnet-4-5-20250929` k=3, grader
fingerprint `72a6c7bd363d`, seed 7, `CLEW_WIRE=compact`. Comparator: `acceptance/runs/1.3.0-final/`.

> **Correction (2026-11-17).** The judge named above is wrong. Every grade of this run records `judge_model: claude-sonnet-5-5` (189/189) — the provider-canonical id adopted in 844fee55 and disclosed in the 1.2.0 pre-registration. `claude-sonnet-4-5-20250929` was text carried over from an earlier record. The figures are unaffected: they were measured with what the grades record. Found by the 2.0.0 rubric cross-check; `tests/test_run_records.py` now checks every run's record against its grades. The line above is left as published.


## Judge integrity

| pass | errored samples | rate | split decisions |
|---|---:|---:|---:|
| grid grading (usage limit reached mid-grade) | 1,020 / 3,888 | 26.23% | 387/1,296 (29.9%) |
| repair 1 (all four targets; limit reached again during mbedtls) | 747 / 3,888 | 19.21% | 302/1,296 (23.3%) |
| repair 2 (all four targets, after a confirmed reset) | **0 / 3,888** | **0.00%** | **63/1,296 (4.9%)** |

Method: `scripts/judge_error_rate.py acceptance/runs/1.4.0-final`. A repair pass re-runs
`acceptance grade` per target; cached successful samples replay, only errored samples are re-judged.

## Gate — per repo, index_only arm (pre-registered)

Method: `scripts/gate_figures.py acceptance/runs/1.4.0-final acceptance/runs/1.3.0-final`
(reproduces 1.3.0-final's published figures; `tests/test_gate_figures.py`).

| repo | tokens 1.3.0 | tokens 1.4.0 | cost | separation 1.3.0 | separation 1.4.0 | quality (≥ 1.3.0 − 3.0) | gate |
|---|---:|---:|---|---:|---:|---|---|
| mattermost | +13.6% | −12.3% | ok | +1.37 | +0.00 | ok | PASS |
| mbedtls | −17.0% | −29.7% | ok | +2.55 | −4.51 | **miss** (floor −0.45) | **MISS** |
| self | −70.0% | −66.3% | **miss** | −5.92 | −5.41 | ok | **MISS** |
| entropic | −34.6% | −46.8% | ok | −7.01 | −9.80 | ok | PASS |

**The gate is NOT met: 2 of 4 repos miss** (mbedtls on quality, self on cost).

## index arm (reported, not gated)

| repo | tokens 1.3.0 | tokens 1.4.0 | separation 1.3.0 | separation 1.4.0 |
|---|---:|---:|---:|---:|
| mattermost | +28.2% | −7.6% | +6.79 | −0.84 |
| mbedtls | +27.8% | −3.0% | +2.60 | +5.05 |
| self | −57.7% | −40.3% | −8.72 | −7.83 |
| entropic | +20.6% | −17.8% | −0.76 | −10.39 |

## Baseline drift (this grid's baseline vs 1.3.0-final's; never folded into a separation)

| repo | baseline score | baseline tokens |
|---|---:|---:|
| mattermost | +6.10 pt | +24.7% |
| mbedtls | −0.16 pt | −3.5% |
| self | −2.97 pt | −19.8% |
| entropic | +2.99 pt | +17.0% |

## Absolute total tokens per arm, 1.4.0-final vs 1.3.0-final (same rubric, same model)

| repo | baseline | index_only | index |
|---|---:|---:|---:|
| mattermost | +24.7% | −3.7% | −10.1% |
| mbedtls | −3.5% | −18.2% | −26.7% |
| self | −19.8% | −9.8% | +13.0% |
| entropic | +17.0% | −4.9% | −20.3% |

Method: `gate_figures._tokens` summed per arm in each run. The gated figure is a ratio to the
same grid's baseline, so baseline drift moves it: mattermost's and entropic's baselines rose
+24.7% / +17.0%, which accounts for most of their index_only "vs baseline" improvement; self's
baseline fell −19.8%, so its index_only arm fell less (−9.8%) and the ratio missed.

## Per-cluster separations (index_only / index), points

| repo | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 |
|---|---|---|---|---|---|---|
| mattermost | −11.11 / −4.44 | 0.00 / −3.33 | +11.11 / +16.67 | 0.00 / −4.76 | 0.00 / −8.33 | — |
| mbedtls | +26.67 / +23.33 | +3.03 / 0.00 | −18.39 / +12.64 | −16.00 / 0.00 | −17.86 / −10.71 | — |
| self | +4.17 / 0.00 | −23.81 / −22.22 | −6.17 / −8.64 | −21.84 / −27.59 | +2.47 / +9.88 | +12.70 / +1.59 |
| entropic | +3.17 / −4.76 | −17.95 / −10.26 | −11.11 / −6.67 | −12.35 / −13.58 | −10.78 / −16.67 | — |

3 replicates per arm; between two 1.3.0 grids on an unchanged rubric, single clusters moved by up
to 20 pt, so a single cluster is not evidence on its own.

## Not yet established

- why mbedtls index_only Q3–Q5 fell (−18/−16/−18 pt) while the index arm on the same clusters did not;
- whether the baseline token drift (+24.7% mattermost, −19.8% self) is model drift or replicate noise.

No release action is taken on these results without the owner's decision.

> **Grader moved after this run (2026-11-17).** This run was graded at `72a6c7bd363d`. For the 2.0.0 grid the grader matches set members on whole path segments instead of the last segment (`include/mbedtls/*.h` had folded to `*.h`), at fingerprint `c10cf554ae6d`; these cells are not re-gradable at the new fingerprint.
