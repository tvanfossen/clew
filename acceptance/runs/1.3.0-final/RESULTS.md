# 1.3.0 — second re-run (`1.3.0-final`)

**The pre-registered release gate (Decision B) is NOT met on the held 16.** Mattermost-mobile,
the TypeScript target this release was rescoped for, moved from a −10.26 pt `index_only` loss to
a +1.37 pt gain. Both statements are reported; neither is averaged into the other.

Tool at `7037358` (clean), version 1.3.0, build 9. Answering model `claude-haiku-5-5`, judge
`claude-sonnet-4-5-20250929`, grader `72a6c7bd363d` (frozen), seed 7, 3 replicates, 189 cells.
Criteria and every tool change since the first pre-registration: `../1.3.0-pending/PRE-REGISTRATION.md`
(addendum 2 lists what can move the held 16).

## Judge health — publication gate passed

| | |
|---|---|
| judge samples | 3,888 |
| errored | **0** (0.00%, threshold 2%) |
| split decisions | 75 / 1,296 votes, **5.8%** (non-zero: k=3 voting is live) |

**Two repair passes, disclosed.** A claude.ai usage limit was reached during grading: after the
first pass 880 samples (22.6%) had errored, all from the outage window. Repair pass 1 (re-run of
`acceptance grade` per target; cached successes replay, errors are never cached, so only errored
samples were re-asked) brought it to 382 (9.8%) before the limit was reached again; repair pass 2,
mbedtls only, after a confirmed reset, brought it to 0.

## Figure 1 — held-16 delta, the gate

Separation = arm mean − baseline mean per (target, question) cluster, averaged over clusters.
Method reproduces 1.2.0's published −1.58 / +1.56 exactly.

| | `index_only` | `index` |
|---|---:|---:|
| comparator (1.2.0 answers re-graded at `72a6c7bd363d`) | −0.05 | +2.52 |
| first 1.3.0 grid (`2697f35`, `../1.3.0-pending/`) | −0.38 | +2.23 |
| **this run** | **−3.62** | **−2.70** |

| cost, held 16, vs baseline | output | cache read |
|---|---:|---:|
| 1.2.0 published `index_only` | −38.2% | −53.4% |
| **this run `index_only`** | **−41.9%** | **−51.8%** |
| this run `index` | −15.4% | −18.2% |

Decision B: (a) separation higher than −0.05 — **no**; (b) separation within 1 pt of −0.05 with
a cost reduction more than 5 pt better — **no** (the cost holds; the separation does not). The 1-
and 5-point margins are declared tolerances, not statistical thresholds.

## Figure 4 — baseline drift, reported beside the delta

**The baseline arm scored +4.23 pt higher than the comparator's baseline** on the held 16, with
no MCP server involved. A separation is relative to its baseline, so this moves every separation
above. In absolute arm score against the comparator: `index_only` **+0.66 pt**, `index`
**−0.99 pt**. That decomposition is arithmetic on the table above, not a claim about cause; the
model behind `claude-haiku-5-5` is pinned by id and still moved its baseline this much between
grids, which is the confound `#28` (dropped from 1.3.0) was meant to remove.

Per-cluster separations swing by up to 20 pt between the two 1.3.0 grids on an unchanged rubric
(e.g. entropic Q3 `index_only` −8.9 → −26.7; mbedtls Q1 +21.7 → +41.7), so at 3 replicates a
single cluster's movement is not attributable to a tool change.

## Figure 2 — full grid (21 clusters)

`index_only` **−2.43**, `index` **−0.44**. Not a delta: the held 16 and mattermost are different
cluster sets.

## Figure 3 — mattermost-mobile (TypeScript / JSX / React Native)

| | `index_only` | `index` |
|---|---:|---:|
| first 1.3.0 grid (`2697f35`) | −10.26 | −0.64 |
| **this run** | **+1.37** | **+6.79** |

Per question, `index_only` / `index`: Q1 +2.2 / 0.0 · Q2 −3.3 / +3.3 · Q3 +5.6 / +24.1 ·
Q4 +2.4 / +2.4 · Q5 0.0 / +4.2.

| cost vs baseline | output | cache read |
|---|---:|---:|
| first grid `index_only` | −4.1% | +32.6% |
| **this run `index_only`** | **−19.7%** | **+12.6%** |
| this run `index` | −3.8% | +29.1% |

Cache read is still above baseline on mattermost: the TypeScript answers carry larger dossier
bodies than the C/Python targets.

## Wall time

Summed `duration_ms` per arm: held 16 `index_only` −40.2%, `index` −19.3%; mattermost
`index_only` −19.2%. KNOWN-DEFECTS 3 (method of 1.2.0's published wall figure) still applies.

## Known defects carried

`../1.3.0-pending/KNOWN-DEFECTS.md` — split rate counts an errored sample as disagreement (moot
here at 0 errors); grading spans usage windows; wall-time method; judge calls persist a session
each (pruned after every pass with `scripts/prune_judge_sessions.py`).
