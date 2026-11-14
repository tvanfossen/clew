# 1.4.0 — pre-registration

Written BEFORE the grid, on owner approval of a full pre-registered grid (2026-11-13). The tool
commit, grader, models, seed and replicates are fixed here; the run must not start from a dirty
tree (`runner.check_tool_tree`).

## What is measured

The post-1.3.0 work on `feat/1.3.1`: the export API (no agent effect expected), the two-tier
refresh (no agent effect expected — a grid builds each index once), and the TOKEN-COST track:

| change | expected effect on an index-arm answer |
|---|---|
| 1.3.7 short `qualified`, compact neighbour rows (`CLEW_WIRE=compact`, as the plugin ships) | smaller dossier replies |
| 1.3.8 served text 15,731 → 10,189 chars | smaller fixed prefix per turn |
| 1.3.9 docstring served once (compact) | smaller Python dossiers |
| 1.3.10 over-cap batches answered; `::`/`.` selectors; file-scope code search | fewer wasted calls |
| W1–W6 wiki | none on the grid (no tool reaches it) |

The index arms run with the plugin's server environment (`acceptance/provision.py` reads
`.claude-plugin/plugin.json`), so they measure the compact shape a plugin user receives.

## Fixed parameters

| | |
|---|---|
| targets | mbedtls, entropic, self, mattermost (the 1.3.0-final four, same pins) |
| arms | baseline, index_only, index |
| model | claude-haiku-5-5 (answering), claude-sonnet-4-5-20250929 (judge, k=3) |
| grader | `acceptance/grader/` unchanged — fingerprint 72a6c7bd363d |
| replicates / seed | 3 / 7 — 189 cells |
| comparator | `acceptance/runs/1.3.0-final/` (same targets, grader, model) |

## Hypotheses, per repo (projected offline with `.claude/tmp/token_model.py` from 1.3.0-final)

Total tokens per answer vs that repo's baseline, index_only / index:

| repo | 1.3.0-final measured | 1.4.0 projected |
|---|---|---|
| mattermost | +13.6% / +28.2% | ≈ +3.5% / +20% |
| mbedtls | −17.0% / +27.8% | ≈ −23% / +22% |
| self | −70.0% / −57.7% | ≈ −72% / −60% |
| entropic | −34.6% / +20.6% | ≈ −38% / +14% |

Quality (separation, points vs baseline), 1.3.0-final index_only / index: mattermost +1.37 / +6.79,
mbedtls +2.55 / +2.60, self −5.92 / −8.72, entropic −7.01 / −0.76. Hypothesis: non-inferior.

## The gate — per repo, both must hold for every repo, for the index_only arm

1. **Cost:** total tokens vs baseline (summed over the repo's cells, the 1.3.0-final method) is
   LOWER than 1.3.0-final's for that repo.
2. **Quality:** separation is no more than **3.0 points below** 1.3.0-final's for that repo.
   A declared tolerance, not a statistical bound: per-cluster separations moved by up to 20 pt
   between two 1.3.0 grids on an unchanged rubric, and the noise floor is still unmeasured.

The `index` arm is REPORTED with the same two figures and is not gated. Baseline drift (this grid's
baseline vs 1.3.0-final's) is reported beside every separation, never folded into it.

## Publication rules

Judge error rate ≤ 2% after repair passes (each disclosed); split rate non-zero. Every figure in
RESULTS.md carries its method. A gate miss is reported as a miss; shipping over it is the owner's
call, recorded as such.
