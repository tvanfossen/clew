<!-- SPDX-License-Identifier: MIT -->
# Matrix result — TEMPLATE

**A pre-registration.** The shape is fixed before the data exists, so the report cannot be
organised around whatever the data turned out to say.

**Fill every section. Delete none. If a section has no data, write why.**

**THIS TEMPLATE NAMES NO TARGET AND MUST NOT ACQUIRE ONE.** Every target-specific fact belongs
in the rubric or in the filled-in result. Writing a repository name into this file means editing
the wrong file.

---

## 1. What this run was

| | |
|---|---|
| Date | |
| Harness SHA | one SHA — if the instrument changed mid-sweep, say so and treat the run as suspect |
| `CLEW_BUILD_VERSION` | |
| Target(s) | one row each: name, link (or "private — not publishable"), and the commit its rubric pins |
| Cells planned / run / valid | |
| **VOID cells** | count, and every one named — see §1a. Not folded into "invalid" |
| `unmarked_pct` | **must be 0** — a mark the judge never ruled on is an unfinished measurement, not a failure |
| **Index provenance — DEFAULT or TUNED** | see §1b. One word, before any metric |
| **Cell isolation** | whether tree and index were restored between cells; if not, name every cell that ran after a mutating one |

## 1a. Void cells — counted and named

A cell whose index answered about a **different repository** than the questions ask about is
VOID. Its marks are meaningless and so are its tokens, because a cell that discovers the wrong
repository and bails costs a fraction of a working one.

| verdict | meaning | accounting |
|---|---|---|
| `ok` | every index reply named the target | graded normally |
| `void` | at least one reply named another repository | excluded from every average, **listed here by cell** |
| `unchecked` | no transcript, or no reply carried a stamp | graded, **but listed here** — "could not check" is not "checked and fine" |

A non-zero `void` count is a configuration failure, not a weak result. Say so before any metric.

## 1b. Which index was measured — DEFAULT or TUNED

The harness **builds nothing**. It serves whatever index exists at the target's canonical
location, and `metrics.csv` records nothing about how that index was built. "The index helps out
of the box" and "the index helps once configured" are different claims.

State, from the target's own `build_meta`:

| | |
|---|---|
| `scope.source` | declared / doxyfile / whole-repo |
| `scope.roots`, `scope.excludes` | as stamped |
| Declaration present? | whether the target ships `.clew.yaml` or `x-clew:`, and what it declares |
| Build options | anything under `options.*` or `preprocessor.*` |
| Verdict | **DEFAULT** (nothing declared, no operator flags) or **TUNED** (say what was declared and by whom) |

A TUNED result is not disqualified. It is a different claim and has to be labelled.

---

## 2. The four metrics, per target and per tier

**Lead with whichever one the index does worst on.** If the index loses on quality, that is the
first sentence of this document.

| # | metric | direction | result |
|---|---|---|---|
| 1 | Answer quality vs the rubric | must improve | |
| 2 | Tokens consumed, as a fraction of the source-arm baseline | must improve (lower) | |
| 3 | Wall time to answer | parity minimum | |
| 4 | Regeneration latency after an edit | low enough to be invisible | |

**Bar:** two of the first three must IMPROVE, the third at PARITY minimum. State plainly whether
it was met. Met or not met — not "broadly met".

### Metrics 2 and 3 survive a rubric change; metric 1 does not

Tokens and wall time measure what a cell cost, so two runs of the same questions under different
keys compare directly. A rubric change moves the denominator, the marks and what counts as a
hit, so quality compares only against another run of the **same rubric**. When the rubric moved,
say so and **print no delta**.

### Bringup — attributed to the index arm, not in the per-question average

| | |
|---|---|
| Bringup events | one per (model, run) on the index arm — **not one per run** |
| Bringup wall time | median and range, from `build_ms` |
| Bringup tokens | median and range |
| Source-arm counterpart | **none, and none is invented** |
| Amortisation | state the N it amortises over, and give the per-question equivalent as a SEPARATE line |

### Metric 2 is stated as a fraction of baseline, paired by question

Write "the index consumed **0.52×** the tokens" — not "1.9× cheaper", which inverts the
intuition and reads as *more*.

Run-to-run token variance is high on both arms and higher on the index arm, because the agent
chooses a handful of queries on one run and dozens on the next. **A per-question token ratio is
uninterpretable and must not be quoted with a verdict attached.** Report this run's own CV — the
tier report prints it per model and arm.

The matrix is nonetheless adequately powered, because the claim is not per-question:

- Each (arm, model, target) has N graded questions × 3 runs. State N.
- Compare **within a question**: same question, same model, same run index, both arms. Question
  difficulty cancels.
- Aggregate the paired differences and report a **confidence interval**, not a point estimate.

| where | how tokens are reported |
|---|---|
| Headline metric 2 | paired, pooled, with a confidence interval |
| Per-question table | descriptive only — median and range, no ratio, no verdict |
| Any single cell | never quoted as evidence of anything |

**If the paired interval spans 1.0, metric 2 is PARITY.** Write that plainly. Against the bar, a
parity result on tokens is a real outcome, not a failed measurement.

Quality is unaffected by this: a mark lands or it does not. Do not import the token caveat into
the quality claim, and do not use token noise to excuse a quality loss.

---

## 3. Tier crossing

Does `haiku + index` reach or beat `sonnet` or `opus` without it?

Two numbers per tier. Do not collapse them into one cross-tier "cheaper" figure — a haiku token
and an opus token are different goods.

> `haiku + index: X% at N tokens` · `sonnet raw: Y% at M tokens`

---

## 4. Per-question breakdown — including every question the index LOST

One row per question, per target. **Losses are not an appendix.** Diagnose to the mark: "a
cluster of marks about one subsystem lost together" is actionable; "the index is 8 points
behind" is not.

Bringup does not appear in this table and is not in the per-question average. See §4a.

## 4a. Bringup verification — index arm only, reported separately

Grades whether the agent established that its view was complete and current **before** answering
anything.

- **Index arm only.** No counterpart exists and none may be invented.
- **Excluded from the per-question average.** It grades behaviour, not understanding of the
  repository; folding it in makes the headline uncomparable against any run without it.
- **Reported as its own line**: pass rate per (model, run), every failure named.

**A failed bringup voids its whole session, not just its cell.** Report the count of sessions
aborted this way beside the void-cell count in §1a.

---

## 5. Pairwise blind comparison

Both orderings judged. A verdict that flips under swap is **unreliable**, not counted. Report
the flip rate; a high one means this axis carries no weight for this run.

---

## 6. Contamination and fairness disclosures

- **Any mark whose grading surface changed after it was first measured.** A fix to a surface the
  rubric grades is also teaching to the test, and the marks it touches stop being comparable.
  Name every one.
- **Any rubric change between this run and the one it is compared against.** Say which rubric
  each quality figure came from.
- **Arm fencing**, and the count excluded from each arm. `arm_only` names the arm that CAN reach
  a mark; backwards understates the source arm and flatters the index. Expected count is zero.
- **Any question re-run**, and why. `metrics.csv` is append-only and aggregates take the last
  attempt. Say how many rows were superseded.

---

## 7. What this run does NOT show

Required. At minimum:

- Local ~4B MoE parity on the read/digest path — out of scope and not measured. Silence here is
  not a negative result.
- Generality beyond the targets measured. Name them; a claim about "codebases" from a set of two
  is a claim about two codebases.
- Anything the sample size cannot resolve (see §2).

---

## 8. Status

> **UNVETTED.** No claim here is a release claim until the owner has reviewed the grading, the
> tests and the matrix. Until then this is a measurement, not a result.
