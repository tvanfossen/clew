# 2.0.0 — pre-registration

Written BEFORE the grid (owner 2026-11-16: push approved; full grid held for 1am, after a usage
reset). Everything in `acceptance/runs/1.4.0-pending/PRE-REGISTRATION.md` holds unchanged —
targets (mattermost, mbedtls, self, entropic), arms, replicates 3, seed 7, grader fingerprint
`72a6c7bd363d`, comparator `acceptance/runs/1.3.0-final/`, and THE GATE AS WRITTEN (per repo,
index_only arm: tokens vs baseline below the comparator's, separation within 3.0 pt of it) —
except the tool commit, recorded by the harness as `clew_commit` (a dirty tree is refused).

Answering model `claude-haiku-5-5`, judge `claude-sonnet-4-5-20250929`. The answering id is
provider-canonical and FLOATS (`acceptance/modelpin.py`): the provider publishes no dated form
for this family, so a model change under the id is possible and would show only in
`answered_by`. Disclosed, not controlled.

`acceptance/runs/1.4.0-final/` (gate missed on mbedtls quality and self cost) is SUPERSEDED by
this run and kept as the record; it is reported beside this one, never inside a gated figure.

## What changed for the measured arms since 1.4.0-final (`clew_commit` 4a0998d7)

Round 3 is mostly the wiki, which no arm calls. What does reach an arm:

| change | reaches |
|---|---|
| served text 10,726 → 9,636 chars per turn (`propose_declaration` tool retired, `index` trimmed to refresh/status/targets) — measured with `.claude/tmp/served_bytes.py` (build_server, empty registry) at both commits | every index arm, every turn |
| Python call edges through a module alias (`import m as a; a.f()`), and a parameter no longer bound to a same-name pytest fixture (P0) | self (Python); mattermost/mbedtls/entropic carry little or no Python |
| `CLEW_BUILD_VERSION` 9 → 10 (`requirement_links`); a requirement dossier carries `satisfies` / `satisfied_by` | every index rebuilds once in provisioning; requirement dossiers only |
| `git_argv` adds `--no-ext-diff` to diff-family commands | no arm (the gate's impact report) |

## Hypotheses, per repo (index_only, vs 1.3.0-final, the gate)

Method: 1.4.0-final's measured token totals per arm (`gate_figures._tokens`), less the served-text
saving re-read from cache each turn — (10,726 − 9,636) / 4 tokens × that arm's measured turns.
The method reproduces 1.4.0-final's published figures before the subtraction.

| repo | 1.4.0-final tokens vs baseline | projected 2.0.0 | comparator 1.3.0-final | 1.4.0-final separation | expected |
|---|---|---|---|---|---|
| mattermost | −12.3% | −13.1% | +13.6% | +0.00 | PASS |
| mbedtls | −29.7% | −30.5% | −17.0% | −4.51 (floor −0.45) | **MISS on quality** — nothing in this round addresses its Q3–Q5 fall |
| self | −66.3% | −66.7% | −70.0% | −5.41 | **MISS on cost** — the served-text saving (≈1%) does not close 3.7 pt |
| entropic | −46.8% | −47.4% | −34.6% | −9.80 | PASS |

STATED PLAINLY: this round is not expected to fix the two misses. The grid measures 2.0.0 as it
will ship; the release decision on these figures is the owner's.

Variance: single clusters moved by up to 20 pt between two 1.3.0 grids on an unchanged rubric,
and 1.4.0-final's baselines drifted +24.7% (mattermost) / −19.8% (self) in tokens. Baseline drift
is reported as its own figure, never inside a separation.

DISCLOSED CONFOUND, self only (unchanged from 1.4.0-final): its rubric asks about clew, so
served text and clew's own docs can answer it; P0's Python fixes also change self's call graph.
A self quality gain is weak evidence about the index.
