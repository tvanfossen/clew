<!-- SPDX-License-Identifier: MIT -->
# Pre-registration — 1.3.0, written before any cell was generated

**Committed as its own act, before the grid runs.** Every number this directory later holds is
to be read against the criteria below, whichever way they land.

**Decisions A and B below were taken by the owner at the pre-release review, 2026-11-01, before
any cell of this grid was generated.**

## What changed since 1.2.0, stated before the numbers

| what | from → to |
|---|---|
| `grader_fingerprint` | `5489758d9a50` → `72a6c7bd363d`, ONE move |
| `rubric_digest`, mbedtls / entropic / self | **unchanged** — `bbf6195f605be452`, `705c131e354e5c22`, `d8447c7b18eafbf5` |
| targets | + mattermost-mobile (`32294778c2753056`), the first TypeScript/JSX target |
| judge / answering model | unchanged — `claude-sonnet-5-5` / `claude-haiku-5-5`, both floating |
| build version | 8 → 9 |

**THE GRADER MOVE IS THE ONE TO READ FIRST.** 1.2.0's `RESULTS.md` already disclosed that its
k=3 votes were not votes: the verdict cache keyed on prompt and model, so samples 2 and 3
replayed sample 1. `891b73d` keys each sample separately. So **1.2.0's scores are single-sample
and 1.3.0's will be genuinely voted** — on the same rubrics, the same marks and the same judge.
Majority voting changes which way a borderline mark falls, and nothing guarantees that change is
symmetric between arms. A held-16 delta read straight across the two runs would credit or charge
clew for a grader repair. Decision A removes that confound.

**No held rubric was edited.** `git log v1.2.0..HEAD -- acceptance/targets/{mbedtls,entropic,self}`
is empty; a reader who does not trust this sentence should run it.

### The clew changes that can move the held 16

`#35` (JSX edges) and the `forwardRef`/`memo` definitions touch only JS/TS trees; none of the
held targets has one. These four are cross-language and CAN move a C or Python target:

- `unresolved_inbound` credits a dispatch family (entropic: share of inbound-less functions
  carrying a count 0.8% → 5.6%) — changes reply content on interface methods;
- the doxygen failure / partial-index stamp and its disclosure — changes the build path;
- the scope refuses a silent git fallback and discloses committed vendored trees;
- self-declared generated files lose search ties — mbedtls commits nineteen generated files.

The generation-only probe (`acceptance/runs/1.3.0-probe/PROBE.md`) found no sign that any of
these broke the index arm on mbedtls. It made no quality claim and this file does not borrow one
from it.

## What is pinned

| | |
|---|---|
| targets | mbedtls `068ff080b369`, entropic `6dcb4c814639`, self `a6dd8ed919e6`, mattermost `4d842026f691` |
| questions | held 16 (5 + 5 + 6) + mattermost 5 = 21 |
| arms | `baseline`, `index_only`, `index` — **all regenerated** (owner, 2026-11-01: no baseline reuse) |
| replicates | 3 → **189 cells** (144 held + 45 mattermost) |
| answering model | `claude-haiku-5-5` |
| judge | `claude-sonnet-5-5`, k=3 now genuinely voted |
| `grader_fingerprint` | `72a6c7bd363d` — frozen since 2026-11-01 |
| seed | 7 |
| clew tree | must be clean: `generate` and `provision` now REFUSE a modified or unidentifiable tree |

## Four figures, never averaged together

1. **held-16 delta vs 1.2.0** — the release gate. Same 16 `(target, question)` clusters.
2. **full-grid figure** — 21 clusters, this run only.
3. **mattermost as a FIRST BASELINE** — no delta exists and none is computed.
4. **baseline drift** (owner, 2026-11-01) — 1.3.0 baseline arm vs 1.2.0 baseline arm on the held
   16, reported beside figure 1 so a reader sees how much of any delta the floating model moved.
   1.2.0's baseline already drifted +3.1% output and +17.7% wall against 1.1.0 with no MCP server
   in the loop.

A 21-cluster mean against a 16-cluster mean is not a delta and is never presented as one.

## The criteria, fixed now

### 1. Quality — the release gate

**Decision A — the comparator is 1.2.0's own answers, RE-GRADED at `72a6c7bd363d`** (owner,
2026-11-01). The held-16 delta then compares like with like: the same 1.2.0 answers and the
same 1.3.0 answers, judged by one grader with real voting.

- The re-grade runs on a **COPY** of 1.2.0's frozen answers and judge cache, under
  `acceptance/runs/1.3.0-pending/regrade-1.2.0/`. Grading overwrites a cell's `.grade.json`, so
  re-grading in place would edit a published artifact; `acceptance/runs/1.2.0-pending/` is not
  touched, and its figures stand as published at their own fingerprint.
- Sample 0 of every vote replays from the copied cache; samples 1 and 2 are new judge calls.
- This is the SAME version's answers under a grader repaired for a defect its own RESULTS.md
  disclosed — not a different tool re-scored to manufacture a comparator, which is what the
  owner ruled out for 1.1.0.
- The re-graded figures are reported beside 1.2.0's published ones, and the difference between
  them is itself reported: it is the size of the voting repair.

**Decision B — what "improvement over 1.2.0" means** (owner, 2026-11-01). The gate PASSES when
either holds, on the held 16, `index_only` against `baseline`:

- **quality improves without cost shifting**: the separation is HIGHER than the re-graded
  comparator's, AND output and cache-read reductions each stay within 5 points of 1.2.0's
  (−38.2% and −53.4%, so no worse than −33.2% and −48.4%); OR
- **cost improves without quality shifting**: the separation is within 1 pt of the re-graded
  comparator's, AND output or cache-read reduction is more than 5 points better than 1.2.0's.

No noise floor is measured on this grid (one grading pass), so the 1- and 5-point margins are
**declared tolerances, not statistical thresholds**, and the report says so in those words.

### 2. Judge error rate — a publication gate, unchanged

**If more than 2% of judge samples error, the run is reported as degraded and the quality figure
is withheld.** k=3 now makes three real calls per vote, so this run makes roughly three times the
judge calls 1.2.0 actually made; a capacity-driven error spike is likelier, and is a stop.

### 3. Split rate — now a real measurement

1.2.0's split rate could not be measured: its votes were one call counted three times, so
agreement was 1.0 by construction. This run's split rate (`scripts/judge_error_rate.py`) must be
**non-zero**. A zero would mean the k=3 fix did not take effect and voids criterion 1.

### 4. Cost

`output_tokens` and `cache_read_tokens` reported separately, never summed. The MCP-instruction
confound recorded since 1.1.0 is unresolved and still applies.

## What would falsify the work

- the held-16 separation is lower than the comparator's → published with its sign; the 1.3.0 tag
  waits (owner's gate)
- the separation improves but a cost axis regresses beyond tolerance → the gate is not met
- split rate zero → the grader fix did not take; no quality figure
- judge error rate above 2% → no quality figure from this run at all

## What this run may not do afterwards

No rubric edit, no mark reweighting, no question exclusion, and no grader change after the
numbers exist. A defect found in the grader *by* this run is recorded and fixed for the NEXT
run; it does not re-score this one.

## Addendum, 2026-11-02 — written before the re-run, after a superseded grid

**A grid ran at `f9e98a5` and is superseded, unanalysed.** Its 189 cells were generated; its
grading hit two usage-limit outages (judge errors 42.2%, then 11.3% after one repair) and never
reached the 2% gate. No quality figure was computed from it, and none will be. Its artifacts are
kept, untracked, in `acceptance/runs/1.3.0-superseded-f9e98a5/`.

**WHY IT WAS SUPERSEDED, stated so it cannot read as discarding a bad number:** no figure from it
existed. During the outage the owner asked whether every TypeScript concern was answered; a
measured audit of mattermost-mobile's index then showed the TypeScript harvest was materially
incomplete, and the owner ruled 1.3.0 must not ship partial support. The fixes changed the index
the grid would have measured, so its cells described a tree that would not be tagged.

**What changed in the tool since this file was first committed** (`be873a8`), each measured on
mattermost-mobile at `4d842026` and recorded in its commit:

| commit | change |
|---|---|
| `fc51089` | TypeScript mixin classes are classes; inherited `this.` calls resolve through declared bases; a call is credited to the INNERMOST enclosing function |
| `d988734` | any wrapper around a function literal binds that function (owner's ruling over an allowlist) |
| `563f43a` | interface signatures and object-literal functions are definitions; signatures never split attribution |
| `f2c919d` | named closures are definitions; a bare call resolves lexically first |
| `cf057c4` | a member call reaches a free function only through what holds it |
| `640977c` | typed class members; an interface-typed receiver reaches its implementation family |
| `313e4eb` | the gate checks mixin members and stays a subset of the index |

Net on mattermost: functions 6,884 → 10,015 · resolved call edges 12,439 → 16,357 · unresolved
inbound sites 4,266 → 2,194.

**CROSS-LANGUAGE EFFECTS, because they bear on the held 16.** Most of the above is gated to
parse-built (JS/TS) definitions. Two changes are not: the innermost-caller rule applies to every
language's call-site attribution, and the inherited-method lookup sits in the shared resolver
(its Python end-to-end case passed without it, because doxygen's own cross-references already
resolve `self.helper()`). Both can move the held targets' indexes; the held-16 delta is therefore
read against them as well as against the TypeScript work.

**Unchanged:** the rubrics (digests as above), the grader (`72a6c7bd363d`, frozen), the judge and
answering models, the seed, the replicate count, Decisions A and B, and the comparator — 1.2.0's
answers re-graded at `72a6c7bd363d` in `regrade-1.2.0/`, 0 judge errors after an outage repair
that re-asked only errored samples (errors are never cached, so successes replayed unchanged).

**Grading will be paced across usage windows.** One grid's judging (~3,900 real k=3 samples)
does not fit a single window; each grading pass starts after a confirmed reset, with repair passes
between, until the judge error rate is under 2%. Every repair pass is disclosed in RESULTS.md.
