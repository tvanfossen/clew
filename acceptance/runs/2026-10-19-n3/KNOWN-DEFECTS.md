<!-- SPDX-License-Identifier: MIT -->
# Known defects in this run

Every figure below was verified against the artifacts. An adversarial audit (2026-10-25) found
most of them; three were corrections to this file's own earlier numbers, and those are marked.
For each defect: what it is, and whether it moves the published **separation** or only the
absolute scores — because the separation is what is published.

## The published claim

> `index_only` versus a shell-only `baseline`, 144 cells, 3 repositories, haiku 5.5:
> **−13.92 pt completeness**, 48 pairs in **16 (target, question) clusters**,
> **cluster-robust SEM 3.31 pt → 4.2σ**.
> Cost, PROVISIONAL (see defect 6): −35.2% output tokens, −39.2% cache-read, −27.7% wall,
> at statistically equal turns and tool calls.

**Robustness.** The sign does not move under any defensible exclusion: published −13.92;
drop the contaminated mbedtls Q3+Q4 −11.16; drop `self` entirely −17.93; drop every pair
carrying unruled weight −14.11; strip the `:line` key defect −14.29; drop saturated decisions
−19.97; drop never-hit decisions −16.35; drop both −24.50. Range −11.2 to −24.5, all negative.
The published figure sits near the **conservative** end.

---

## 1. The judge is not arm-blind. DISCLOSED HERE FOR THE FIRST TIME

`DESIGN.md` claimed *"one judge call gets one mark's text and the anonymised answer. Not the
arm…"*. The prompt is clean — `grader/judge.py` sends one mark text plus the answer and nothing
else. **The answer text itself identifies the arm.** Measured after running every answer through
`anonymise`, on entropic + mbedtls (where "index" is not a domain word):

| the word "index" survives anonymisation | count |
|---|---|
| baseline | **3/30** |
| blended `index` | 15/30 |
| `index_only` | **30/30** |

A judge could name the arm from the text at roughly 95% accuracy. Two of `anonymise`'s three
substitutions are also inert: the `mcp__` rewrite fired on 0 of 144 answers, and the header strip
matches nothing because answers carry no `# Qn —` line.

**Not fixed by scrubbing, deliberately.** Removing "index" from an answer edits the evidence.
**Direction: probably deflates `index_only`.** Its characteristic prose — "no shell", "cannot
read", "the index does not hold" — appears in 20 of 48 of its answers against 2 of 48 for
baseline, and that hedging is exactly what a completeness rubric reads as a miss. `DESIGN.md`'s
claim is retracted rather than the scrubber strengthened.

## 2. Four cells publish a transport failure as a score of zero

`self` Q6 `index_r1`, `index_r2`, `index_r3` and `index_only_r3` each carry
`score = 0.000, unmarked_pct = 1.000`, and every decision reads
`1/1 calls failed: rc=1 after 4 attempt(s)` with `duration_api_ms: 0` — the judge CLI never
reached the server. Six further `self` Q6 cells are 33–95% unruled.

**This is the defect that most embarrasses the documentation.** `DESIGN.md`,
`PRE-REGISTRATION.md` and this file's earlier version all asserted that *"an unruled decision is
never a miss"*. The code does the opposite: `QuestionResult.score` puts unruled weight in the
DENOMINATOR and leaves it out of the numerator, which is arithmetically identical to a miss.

**Effect on the separation: −0.19 pt** (dropping all three `self` Q6 pairs gives −14.11). Effect
on absolute scores and on any `self` Q6 figure: invalid. No `self` Q6 number may be quoted.

## 3. Per-arm `unmarked_pct` is one broken question, not an arm property. CORRECTS THIS FILE

An earlier version of this file reported "baseline 3.3%, index_only 5.8%, blended 8.4%" as per-arm
rates. Excluding every pair carrying any unruled weight removes **exactly 3 pairs, all self Q6,
and nothing else.** Those three numbers are one question's judge outage divided across arms, and
reporting them per arm invites the inference that the blended arm is somehow harder to grade.
Withdrawn.

## 4. The scorer's set key does not strip a `:line` suffix — run-wide, not two marks. CORRECTS THIS FILE

`grader/score.py:_key` strips backticks, quotes and a trailing slash, takes the basename and
lowercases. It does not strip `:NNN`. So an answer naming the right file with its line number is
scored as naming something spurious. **14 of 114 precision decisions** fail this way, on all
three targets (baseline 6, blended 6, `index_only` 2).

Worst case, `mbedtls` Q1 `index_only_r1`: the answer named **both** correct set members with
correct line numbers — `benchmark.c:430` and `ssl_pthread_server.c:277` — and scored **0 of 3** on
a weight-2 set mark. Six of that question's twenty weight units, −30 pt on the question, from
string matching.

An earlier version of this file described this as a parenthetical about one entropic file inside a
section about two unpassable marks. The scope was wrong. **Effect on the separation: −0.37 pt**
(re-keying gives −14.29), so it mildly *flatters* `index_only` as published.

## 5. Saturated and never-reached decisions, both larger than this file claimed. CORRECTS THIS FILE

Of **191 distinct decisions** across the run: **40 are hit by every arm in every replicate**, and
**33 are hit by nobody, ever**. On entropic alone: **61 decisions, 16 saturated**.

An earlier version said *"ten of 48 entropic marks are saturated"*. Neither number reproduces
against any denominator in the artifacts. `AGENTS.md`'s own rule — *a figure whose method cannot
be reproduced gets removed rather than re-derived* — applies to this project's own file, so it is
replaced by the measured counts above rather than adjusted.

Two unpassable precision marks were previously described; the real count of decisions no arm ever
reached is **33**. Both entropic cases remain diagnosed: Q3's member list omits
`config.local.yaml` and `permission_persister.cpp` while its extract instruction asks for files
"recording that decision", and Q5 rejects `scripts/gen_bindings.py` eight times while asking for
files "declaring the bindings".

**Direction: both classes compress the gap**, since every arm scores them identically. Removing
both gives **−24.50 pt**, so the published −13.92 understates the discriminating difference by
roughly a factor of two. The audit's independent count of never-hit decisions was 20 against this
file's 33; the discrepancy is unresolved and the larger, less favourable figure is published.

## 6. The cost claim is confounded by coaching only the index arms. PROVISIONAL

The index arms receive, in their system prompt, `clew/mcp_server/server.py`'s ~1,900-character
`INSTRUCTIONS` block plus three long tool descriptions — *"START AT `dossier` … in ONE call"*,
*"DO NOT OPEN A SESSION WITH `index(action='status')`"*. The briefs are asymmetric too: baseline
67 characters, `index_only` 299. **Every one of those surfaces pushes toward fewer, larger calls,
which is precisely the axis the cost claim measures.**

`runner.check_symmetry` guards only the brief, and its own docstring concedes it cannot verify
that two sentences license the same behaviour. Nothing anywhere disclosed the MCP surface. That
the sensitivity is real is already measured: `runs/2026-10-20-skills-ab` exists because adding a
usage document to the system prompt moves entropic's `index_only` separation to −24.40.

**The cost figures are therefore labelled PROVISIONAL**, pending either equalising the coaching
or measuring its contribution. For the quality claim this is conservative — the coached arm still
loses by 13.92 pt.

Also unstated previously: the quoted figures are **ratios of means**. Means of per-pair ratios are
−32.5% / −31.6% / −23.4%, so the published estimator is the more favourable of the two in all
three axes. `PRE-REGISTRATION.md` requires cache-creation and cost to be reported alongside:
**cache-creation −14.0%, cost −25.4%.**

## 7. The standard error was understated. CORRECTS THIS FILE

An earlier version published **2.60 pt SEM and ~5.3σ**. The 48 pairs are not independent draws:
they are **16 (target, question) clusters of 3 replicates**, and replicates are tightly correlated
— `mbedtls` Q4 is −40.0 pt in all three with byte-identical hit patterns in both arms.

| estimator | SEM | sigma |
|---|---|---|
| naive, n=48 | 2.45 pt | 5.7σ |
| **cluster-robust, 16 clusters** | **3.31 pt** | **4.2σ** |
| target-level, 3 clusters | 3.58 pt | 3.9σ |

The cluster-robust figure is published. The result remains resolved; the precision claimed
earlier does not. Replicates are genuine rather than duplicated answers — 0 of 48
(target, question, arm) groups hold byte-identical replicates — they are simply correlated, which
`n=48` does not price in.

## 8. The noise floor rests on a deliberately mid-range, arm-unbalanced subset

21 cells re-graded, mean absolute pass-to-pass spread **8.95 pt**, median 7.69, max 30.0, signed
mean **+1.56 pt** (so the judge is unbiased, merely high-variance). All 21 carry the same
`rubric_digest` and the same `grader_fingerprint` as pass 1, so this measures judge noise and not
the grader-change confound that fingerprint exists to catch.

But the 21 cells all score **42.9–59.3** against a run spanning 0.0–100.0, and the run holds 17
cells below 20 and 6 above 90, none represented. Selection was deliberate — noise is largest at
the decision boundary — so **8.95 overstates the run-wide floor**, which is conservative for a
claim of a loss. The subset is also arm-unbalanced (10 `index_only`, 6 baseline, 5 blended), and
n=21 puts roughly ±2.8 pt on the floor estimate itself.

`8.95 pt` is a mean absolute difference, not a per-cell standard deviation; using it as one is a
category error, and it happens to land conservative.

## 9. Pass 2 was never run on the 144 cells, so the pre-registered criterion was not met

Every one of the 144 `.grades.jsonl` files holds exactly one line. `PRE-REGISTRATION.md` defines
parity against a floor measured by grading the identical answers twice; the 21-cell subset is a
substitute, not that measurement. **No parity claim is made from this run** — the published figure
is a 13.92 pt loss, which is a difference, not a parity test.

`PRE-REGISTRATION.md` limitation 6 also states the grid is *"INCOMPLETE as a cost result until
zephyr lands"*. It has not landed. Defect 6's provisional label is required by that limitation as
well as by the coaching confound.

## 10. Tool counts were 2x inflated. CORRECTED IN PLACE

`count_tools` counted `tool_use` BLOCKS, and session transcripts repeat rows: one cell held 118
rows against 64 distinct uuids and 30 blocks against **16 distinct ids**. Corrected for all 288
cells by recounting from the frozen transcripts, de-duplicated by `tool_use` id — no API calls
spent. Originals kept as `tool_calls_as_recorded`, with `tool_counts_corrected` naming why.

**The inflation was not uniform** — baseline 1.95x, blended 1.82x, `index_only` 1.70x — so it
moved cross-arm comparisons and not merely absolutes. An 18-cell sample had looked uniform at
1.92–1.94x and was misleading. Fixed in `acceptance/execute.py` `count_tools` v3. The audit
independently recounted 96 of 144 cells from the raw transcripts and matched the stored values
96/96.

Six cells carry no `tool_calls_as_recorded` because their block count already equalled their
distinct-id count. An earlier version of this file said "every cell keeps its original", which was
false.

## 11. `DESIGN.md` does not describe the scorer

`DESIGN.md` states *"A set mark scores its weight only when recall is 1.0 and precision is 1.0"*
and lists all-or-nothing as open ruling 1. `score_set` emits **one decision per member plus one
for precision, each at the mark's full weight** — partial credit, so a weight-2 set mark with
three members contributes eight weight units. Set decisions carry **24% of all run weight**.
`score.py`'s own module docstring documents the real behaviour, so this is a doc-sync failure
rather than a hidden one. `DESIGN.md` is corrected; the scorer is unchanged.

## 12. `run.json` no longer records per-window provenance

All three are dated 2026-10-20 13:34, after the last answer at 2026-10-19 18:39, and each lists
every cell under `resumed` — a no-op `generate --resume` rewrote them, because `cmd_generate`
writes `run.json` before executing cells. The key designed to say *which* cells came from an
earlier window now says "all of them". Everything else in them is correct and matches: seed 7,
rubric digests, clew identity.

## 13. The answering model is an alias

`claude-haiku-5-5`, not a dated snapshot, while the judge is correctly pinned to
`claude-sonnet-4-5-20250929` and `grader/rubric.py` refuses an alias there. A third party cannot
reproduce the arms exactly. Disclosed in advance as `PRE-REGISTRATION.md` limitation 3.

## 14. Tool affordance gaps the measurement exposed

Not defects in the instrument; defects in clew, and the actionable output of the exercise.

- `dossier('execute')` returns a definitive negative advising a check of `target` and staleness,
  neither of which was the problem — the symbol is `ServerManager::execute`. One cell asked for
  the bare name **four times** having already called the qualified form successfully. A near-miss
  hint would have ended the loop on the first try. Five of that cell's sixteen calls, 31%, were
  spent on this and on passing file paths to a symbol tool.
- The thread layer records a spawn only when it can resolve a **named** entry function. A
  `std::thread([]{ ... })` doing inline work is not recorded at all. entropic has 9 first-party
  spawns across 7 files; the index holds 4.

## What was audited and found sound

Claim 1's arithmetic reproduces exactly (−13.919 pt, sd 16.97; 34 negative, 11 positive, 3 zero;
all 144 cells present, every `index_only` cell paired). `--strict-mcp-config` on every arm, so
baseline could not see that an index existed. Baseline keeps the full `Read, Grep, Glob, Bash`
repertoire — not an index-versus-grep strawman. `arm_only` is unused in all three rubrics, so no
mark is fenced off either arm. The judge prompt carries no arm, model, target, evidence, refs,
correct set or other marks. Arm order rotates by replicate rather than flipping. Target commits
pinned and verified including a dirty-tree check; rubric digests in every sidecar match the
on-disk rubrics; `grader_fingerprint` uniform across all 144 cells and the floor pass.
`non_index_tool_calls == 0` for all 48 `index_only` cells, so the no-shell fence held.

**The 2026-10-18 relabelling is not data-discarding.** Rubric digests are identical between that
run and this one, so no rubric was touched after a result was seen; and the discarded figure was
marginally *more* favourable (entropic −17.41 against the published −18.49).

**Contamination is bounded and runs against the tool.** `config_defaults` was written because
three mbedtls Q3 marks failed, and is measured on mbedtls Q3/Q4 — named in
`PRE-REGISTRATION.md` limitation 1, in advance, as the weakest evidence in the set. Excluding
those two questions moves the gap from −13.92 to −11.16: the questions clew was taught to are
where it loses hardest. No undisclosed mark written in response to a failed cell was found.
