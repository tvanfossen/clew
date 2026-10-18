<!-- SPDX-License-Identifier: MIT -->
# Pre-registration — what this grid will be read against

**Written before any cell of the three-arm grid was generated, and committed as its own act.**
Every number this directory later holds is to be read against the criterion below, whichever way
it lands.

## Why this file exists

The instrument was changed **twice** after an unfavourable first result. On the two-arm grid
mbedtls came back at −11.4 pt for `index_only`, and in response:

1. the `index_only` brief lost the clause *"an honest gap is the useful answer here"*, which the
   baseline brief never carried — a real confound on a rubric that scores completeness; and
2. the blended `index` arm was added back to the grid.

A third change then landed in the TOOL: `clew/config_defaults.py`, which exists because three
mbedtls Q3 marks scored 0/3 against a shell arm's 2-3/3.

Each change is defensible on its own and each is documented where it was made. The pattern is
not: *measure → dislike the result → adjust the instrument* is how a benchmark becomes a
self-portrait, and `docs/CORE_HYPOTHESIS.md` names that failure already. The protection is to
fix the criterion before the numbers exist, so that nobody — including the authors — can move
the line afterwards.

The owner's stated prior, 2026-10-18, is that the hypothesis is **at least at parity** rather
than behind. That is exactly what this criterion tests.

## The criterion

**Parity = the mean per-question separation across targets falls inside the measured noise
floor.**

The floor is measured, not assumed:

- `grade` runs **at least twice** over the identical frozen answers. `DESIGN.md` already
  requires this and already states that a separation smaller than the floor is *unresolved
  rather than a result*.
- The floor is the observed pass-to-pass spread at one `(rubric_digest, grader_fingerprint)`
  pair, as `report` prints it.
- A separation inside the floor is reported as **unresolved**, never as parity-in-our-favour and
  never as a loss.
- A separation outside the floor is reported with its sign, whichever sign that is.

No fixed threshold is used. A number picked in advance without knowing the floor can declare a
+4 pt result "parity" when the floor turns out to be ±12 pt, which would be a claim about
nothing.

## What is reported alongside, every time

Fixed here so the reporting cannot be selected after the fact:

- **All three axes.** `total_tokens` is never quoted alone; output, cache-read, cache-creation
  and cost stay separate. One measured cell had 534,192 cache-read against 7,292 output.
- **`unmarked_pct` beside every score.** A decision the judge never ruled on is not a miss.
- **Per-question separation, not only the target mean.** A tie at the ceiling is a saturated
  question to replace, not a result to average in.
- **Turns and tool calls per arm.** The cost half of the hypothesis is about round trips, and
  the two-arm grid found `index_only` taking 13.7% MORE turns than baseline — the half with no
  obvious lever.
- **Every arm's score, including the blended one** — but they answer different questions and
  only one of them is the hypothesis. See the amendment below.

## Named limitations, fixed in advance

1. **mbedtls Q3 and Q4 are the weakest evidence in the set.** `clew/config_defaults.py` was
   written *because* those marks failed, and it is measured *on* them. That is teaching to the
   test, disclosed as `docs/CORE_HYPOTHESIS.md` requires. An improvement there is close to
   uninformative; the other targets are where the prior is actually tested.
2. **The `self` target carries the same exposure**, for Q6 and for two marks added at 1.1.0.
3. **One model tier.** `claude-haiku-5-5`, which is a canonical id and not a dated snapshot, so
   the answering arms are not pinned the way the judge and the targets are.
4. **The substrate is unpublished.** The run depends on a fork wheel reporting the same version
   string as the released one; `substrate_languages` in each `provision.json` is the only
   artifact that can tell them apart.
5. **riot is absent, not scored.** It refuses to provision — doxygen exits 2 — and a provisioning
   failure is not a score of zero. See `.claude/tmp/riot-provision-defect.md`.
6. **Three targets first.** mbedtls, entropic and self. freertos, knots and zephyr follow into
   this same run directory. zephyr is the scale test and the one most likely to settle the cost
   question, so the grid is INCOMPLETE as a cost result until it lands.

## What would falsify the hypothesis

Stated here so that it is not negotiable later: if the mean separation across targets is
**outside the floor and negative**, the retrieval claim is not supported at this model tier, and
`docs/CORE_HYPOTHESIS.md` is to be amended rather than the instrument.


---

## Amendment 1 — which arm is the hypothesis (2026-10-18)

**Logged as an amendment rather than an edit, because the entropic COST figures already
existed when it was written.** It changes no criterion: the parity threshold, the noise-floor
method and the falsification condition above are exactly as first committed. What it corrects
is an attribution error in the reporting plan.

As first written, this file said the blended `index` arm answers *"is the shipped shape better
than no index"*. That framing treats an agent's tool-use policy as a property of clew, and the
owner rejected it:

> the retrieval substrate is ALL that is being tested, any given model/service/agent arch might
> use it differently — how it gets used by the end machine is NOT our decision to make

That restores the scope this project already set and which PREDATES this run, so it is not a
goalpost moved. `acceptance/runner.py`, owner ruling 2026-08-22: *"The hypothesis puts adoption
OUT OF SCOPE: the claim under test is whether the index yields better answers more cheaply, not
whether an agent thinks to use it."*

So, fixed:

- **`index_only` vs `baseline` IS the hypothesis test**, on both quality and cost. It is the only
  pair whose difference is attributable to the retrieval substrate, because it is the only pair
  where the substrate is the sole variable.
- **`index` is an ADOPTION OBSERVATION at one model tier**, reported as operational context and
  never as a property of the index. Measured on entropic: the blended arm displaced 11.5% of the
  baseline's shell calls and spent 31% more turns — a statement about haiku 5.5's willingness to
  stop grepping, which a different model or harness would answer differently.
- A cost or quality figure from the blended arm may NOT be quoted as a clew result, in this run
  or in anything citing it.

The occasion for the correction was my own: reporting entropic's blended-arm cost as "the
shipped shape costs more than no index at all", which attributed a consumer's habit to the tool.
