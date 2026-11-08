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

## Addendum, 2026-11-07 — an mbedtls re-measure after `cacf3058` (EXPLORATORY)

Not pre-registered; it does not re-score this run, and the gate above stands as computed. The
owner asked why mbedtls got costlier; the transcripts showed 17 of 23 index-only code searches
returning nothing, because the code corpus was built before AST recovery (1,052 of 4,127 bodies)
and a word matched only whole. `cacf3058` fixed both. mbedtls was re-run at `cacf3058` (45 cells,
same flags) in `../1.3.0-mbedtls-fix/`; its grading hit a usage outage (668 of 945 samples
errored) and one repair pass brought it to 0 errors, split rate 5.7%.

| mbedtls | `index_only` out / cache / wall | `index` out / cache / wall | empty code searches (`index_only`) |
|---|---|---|---|
| 1.2.0 | −29.8 / −42.8 / −33.0 | −11.5 / +6.1 / −16.9 | — |
| this run | −21.3 / −20.3 / −21.5 | +6.8 / +29.3 / −0.3 | 17 / 23 |
| `cacf3058` | **−29.3 / −43.8 / −31.1** | **−2.5 / −3.3 / −4.5** | 9 / 23 |

| mbedtls absolute, baseline / `index_only` / `index` | this run | `cacf3058` |
|---|---|---|
| mean | 58.1 / 60.6 / 60.7 | 61.1 / **51.6** / 61.6 |
| separation | +2.55 / +2.60 | −9.54 / +0.51 |

**Cost recovered; `index_only` quality fell.** Diagnosed from the transcripts: the lost Q4 marks
(error.c is generated; its `error.fmt` input) were lost in a cell with no code search at all —
they turn on whether the agent opened `library/error.c`'s dossier — and Q3's lost marks follow the
same pattern. Swings of this size occurred between grids before the code corpus existed (mbedtls
Q4 `index_only` 66.7 → 48.0, comparator → first 1.3.0 grid). At 3 replicates the drop is not
attributable to `cacf3058`, and is not shown harmless either. The owner kept it in 1.3.0.

Spliced into this run's held 16 (mbedtls cells from the re-measure): separation `index_only`
−7.39, `index` −3.35; cost `index_only` −44.0% output, −55.8% cache.

**Where the gate's shortfall sits.** Per target, separation change from the comparator against
that target's baseline drift: mbedtls −7.8 / +6.3, self −7.2 / +6.4, entropic +5.1 / −0.5. The
two targets whose baseline arm rose about six points lost about seven points of separation; the
one that did not, gained. Absolute held-16 arm scores: `index_only` 50.4 → 51.1, `index`
53.0 → 52.0. This is arithmetic on the tables above, not a measured cause.

## Release decision, 2026-11-07 — the owner shipped 1.3.0 over the gate

**The pre-registered gate was not met, and 1.3.0 was released anyway, by the owner's explicit
decision** after reviewing every criterion above against its measurement. The falsifier "the
1.3.0 tag waits" was honoured: the tag waited for the owner, who then overrode it. Nothing above
was re-scored, re-weighted or excluded to make that decision easier, and the gate's figure
(−3.62 against −0.05) is the one this release is published with.

What the decision rested on, each stated above with its method: the held-16 clew arms are flat in
absolute score while the baseline arm rose 4.23 pt; the per-target shortfall tracks that drift;
cost held or improved on every axis; and mattermost-mobile, the TypeScript target this release
was rescoped for, moved from −10.26 to +1.37 `index_only`.
