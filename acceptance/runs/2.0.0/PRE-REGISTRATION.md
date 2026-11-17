# 2.0.0 — pre-registration

Written BEFORE the grid (owner 2026-11-16: push approved; full grid held for 1am, after a usage
reset). Everything in `acceptance/runs/1.4.0-pending/PRE-REGISTRATION.md` holds unchanged —
targets (mattermost, mbedtls, self, entropic), arms, replicates 3, seed 7, grader fingerprint
`72a6c7bd363d`, the 1.3.0-final and 1.4.0-final records for context, — except the tool commit, recorded by the harness as `clew_commit` (a dirty tree is refused).

Answering model `claude-haiku-5-5`, judge `claude-sonnet-5-5` (corrected 2026-11-17: this line first said `claude-sonnet-4-5-20250929`, copied from an earlier record; every rubric and grade uses `claude-sonnet-5-5`, which also floats). The answering id is
provider-canonical and FLOATS (`acceptance/modelpin.py`): the provider publishes no dated form
for this family, so a model change under the id is possible and would show only in
`answered_by`. Disclosed, not controlled.

`acceptance/runs/1.4.0-final/` is SUPERSEDED by this run and kept as the record; its figures are
reported beside this run's for context.

## What changed for the measured arms since 1.4.0-final (`clew_commit` 4a0998d7)

Round 3 is mostly the wiki, which no arm calls. What does reach an arm:

| change | reaches |
|---|---|
| served text 10,726 → 9,636 chars per turn (`propose_declaration` tool retired, `index` trimmed to refresh/status/targets) — measured with `.claude/tmp/served_bytes.py` (build_server, empty registry) at both commits | every index arm, every turn |
| Python call edges through a module alias (`import m as a; a.f()`), and a parameter no longer bound to a same-name pytest fixture (P0) | self (Python); mattermost/mbedtls/entropic carry little or no Python |
| `CLEW_BUILD_VERSION` 9 → 10 (`requirement_links`); a requirement dossier carries `satisfies` / `satisfied_by` | every index rebuilds once in provisioning; requirement dossiers only |
| `git_argv` adds `--no-ext-diff` to diff-family commands | no arm (the gate's impact report) |

## What is reported — figures, not verdicts

OWNER 2026-11-16: the release decision is the owner's, weighing cost, quality and time against
the features 2.0.0 adds. This run reports measurements; it states no pass/miss verdict and no
tolerance band. The core claim is the index arms against the DEFAULT harness (baseline);
release-to-release differences are context, and differences of a few points are within the
variance below.

Per repo, for index_only and index:

  * total tokens vs baseline, and output / cache-read / cache-create separately
  * separation (arm score − baseline score, points), and per question
  * wall time vs baseline
  * the same figures from 1.3.0-final and 1.4.0-final beside them, for context
  * baseline drift vs 1.4.0-final, reported on its own, never inside a separation
  * judge error rate and split rate (repair passes until errors ≤ 2%)

Method: `scripts/gate_figures.py` (it reproduces 1.3.0-final's and 1.4.0-final's published
figures) and `scripts/judge_error_rate.py`.

## Projected served-text effect, for context

1.4.0-final's measured tokens per arm (`gate_figures._tokens`) less the served-text saving re-read
from cache each turn — (10,726 − 9,636) / 4 tokens × that arm's measured turns. The method
reproduces 1.4.0-final's figures before the subtraction. It covers only the served text; P0's
call-graph fixes and model drift are not projected.

| repo | 1.3.0-final index_only tokens vs baseline | 1.4.0-final | projected 2.0.0 |
|---|---|---|---|
| mattermost | +13.6% | −12.3% | −13.1% |
| mbedtls | −17.0% | −29.7% | −30.5% |
| self | −70.0% | −66.3% | −66.7% |
| entropic | −34.6% | −46.8% | −47.4% |

Separation (index_only, points) at 1.3.0-final / 1.4.0-final: mattermost +1.37 / +0.00, mbedtls
+2.55 / −4.51, self −5.92 / −5.41, entropic −7.01 / −9.80. Nothing in round 3 targets quality on
these questions; no quality projection is made.

## Variance

Single clusters moved by up to 20 pt between two 1.3.0 grids on an unchanged rubric; 1.4.0-final's
baselines drifted +24.7% (mattermost) and −19.8% (self) in tokens from the previous grid, and
mattermost's index_only token ratio moved from +21.6% (1.4.0-pending) to −12.3% (1.4.0-final).

DISCLOSED CONFOUND, self only: its rubric asks about clew, so served text and clew's own docs can
answer it; P0's Python fixes also change self's call graph. A self quality change is weak evidence
about the index.

> **Grader fingerprint (2026-11-17):** `c10cf554ae6d` — set members match on whole path segments (`_matches`), replacing the last-segment key that folded `include/mbedtls/*.h` to `*.h` (found by the rubric cross-check; owner-approved). Supersedes `72a6c7bd363d` named above.
