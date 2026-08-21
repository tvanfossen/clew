<!-- SPDX-License-Identifier: MIT -->

# Core hypothesis

Stated as a hypothesis in the scientific sense — an assertion that predicts a measurable
outcome and names in advance what would refute it. Everything in `acceptance/` is
instrumentation for this page. There is no acceptance without a hypothesis.

## Observation

An agent asked a structural question about an unfamiliar repository reads source. It greps for
a name, opens the file, greps for the caller, opens that file. The cost is round trips and
retrieved bytes; the risk is that it stops before it has the whole answer and reports a
confident partial one.

The same facts — who calls this, what runs on which thread, what this lock protects, what
implements this requirement — are derivable ahead of time and storable as a graph.

## Question

Does giving an agent a queryable index of a repository's enforced documentation change how
well, how cheaply, and how quickly it answers structural questions about that repository?

## Hypothesis

> **H₁ — An agent answering questions about a codebase from a queryable index of its enforced
> documentation gives better answers, for fewer tokens, in less time, than one reading the
> source.**

**Independent variable:** the harness. A default agentic harness — shell, file reads, search —
**with** the index versus **without** it. Not "the index versus grep": a partial or full file read
fails the same way a search does, and fencing the baseline down to one command would measure a
strawman.

**Dependent variables — three, and they are three separate claims about one cause.** The cause
is richer metadata in a lookup:

| # | Axis | Claim | Measured by |
|---|---|---|---|
| **1** | **Quality** | Answers are more complete and more correct | marks met, against a source-derived rubric |
| **2** | **Cost** | Answers cost fewer tokens to retrieve | `total_tokens` **and** `result_bytes`, always both |
| **3** | **Time** | Answers take less wall-clock to retrieve | elapsed per cell |

The three are independent and can move in opposite directions. **A result that wins one axis
and loses another is a real result, not a measurement error**, and is reported as such. Report
the axis that hurts first: the first grid published here led with a cost win and a quality
figure it had not checked, and its verdict was wrong.

### Sub-hypotheses, each independently falsifiable

- **H₁ₐ (quality).** Marks met is higher for the index arm.
- **H₁ᵦ (cost).** Tokens and retrieved bytes are lower for the index arm.
- **H₁꜀ (time).** Elapsed time is lower for the index arm.

### Success is a lattice, not a conjunction

Support does not require all three. **An axis held equal while another improves is a win**, and
the axes are not equally weighted — quality and cost carry the claim, time is the weakest of the
three.

| quality | cost | time | verdict |
|---|---|---|---|
| = | **↓** | = | success |
| = | = | **↓** | success, but weakly |
| **↑** | = | = | success |
| **↑** | **↓** | **↓** | **critical success** |
| ↓ | — | — | failure on the axis that carries the claim |

Any one axis failing is a finding about that axis, never a reason to retire the axis or to report
only the other two. Report the axis that hurts first.

## Null hypothesis

> **H₀ — The retrieval substrate makes no difference on any axis; observed per-target deltas
> are within the noise floor of the measurement.**

**H₀ has not been rejected.** Every per-target delta measured to date sits inside every
independent estimate of the noise floor available. That is the current state of the evidence
and it is why the measurement roadmap exists: n=1 cannot separate a real effect from run-to-run
variance, and no amount of re-reading an n=1 grid will.

Rejecting H₀ requires enough replicates to establish the noise floor first. Establishing the
noise floor is therefore a prerequisite of every quality claim this project makes, not a
refinement of one.

## Auxiliary assumptions

H₁ is only testable where these hold. They are assumptions, not conclusions, and each is
independently checkable.

**Richness.** A thin database cannot replace reading source, and the thinner it is the weaker
the case for replacement. Every question a developer actually asks that the index cannot answer
is a reason to reach for `grep` instead — and a good one.

**A different shape of question.** The index is built for structural questions — "who calls
this", "what implements this requirement", "what reaches this across a thread boundary" — rather
than lexical ones. **Learning to ask the structural kind is part of the claim, not a workaround
for it.**

This is a claim about *cost and completeness*, never about capability. **Every question is
answerable by both arms.** "Does this repo have a mutex?" is a `ctrl-F` for a human and a single
search for either arm; nothing beats a straight read on a single fact, and a rubric that grades
there is measuring nothing. The difference is how many operations and how much consumed context
it takes to reach the **complete** answer — which mutexes are live, what else they touch, and
whether they are part of any real usage of the library.

### What actually differs: where the agent stops

Given unbounded budget both arms converge, so the difference is not capability — **it is where
each arm stops.** An agent reaches down, retrieves an answer, and that answer may invisibly be a
*subset* of the complete one. It does not know it stopped early, and it reports with the
confidence of a complete answer.

It stops because attention degrades over accumulated context, and every file read spends that
budget. Inside a single million-token window, attention at token 1 is not attention at token
900k; across sessions it is worse, because what session 1 established is simply gone. A human
holds "mutex A on thread A affects mutex A on thread B through variable C" for weeks. A model
loses it in hours.

So the practical failure is not a wrong answer. It is **work done twice, or a change made in file
A that breaks file B**, because the relationship was never surfaced. H₁ is therefore a claim about
completeness **at the budget the agent actually chooses to spend**, not completeness at unbounded
budget — which makes quality and cost one coupled measurement rather than two independent ones.

## Scope conditions

The experiment holds these fixed. Each is a boundary of the claim, not a property of it, and each
is stated here so a matrix result is never read as evidence about it. They are measured
separately in `acceptance/operational/`.

**Static tree, fresh index.** H₁ is measured at a pinned commit against an index built from that
commit, so index staleness cannot occur inside the experiment. Under a moving tree the index does
carry a staleness signal — but it is *index-level* and flags **invalidity** better than
**incompleteness**: a body that moved is reported per-symbol, while a new call site in a changed
file produces a silently short list. An experiment designed so a failure cannot occur will
faithfully report that it did not.

**Build cost amortised to zero.** The index arm is handed a pre-built index; the baseline arm has
no setup cost. That is defensible — a real user builds once and works for weeks — but it is
assumed rather than measured, so it is stated rather than inferred from the numbers.

**Adoption is out of scope.** Whether a model *wants* to reach for the index is a separate
problem: models are trained on shell commands and their programmatic history, not on MCP tool
use. That is a question about affordance, not about whether the tool is good. It follows that an
arm *instructed* to prefer the index is not a flawed counterfactual — it is the control that
isolates tool quality from adoption.

**Refresh latency is out of scope.** Every editor-integrated index pays a re-parse delay. It is
machine-bound, it would confound the time axis with an operational variable, and it is measured
in `acceptance/operational/` instead.

## Predictions

If H₁ holds, then on a correct target:

- The index arm reaches a given completeness in fewer round trips than the source arm.
- The index arm's cost is less sensitive to repository size, because a lookup returns a fact
  where a search returns lines to be read.
- The gap widens on questions whose answer spans subsystems, and narrows to nothing on
  questions whose answer is one string in one file.

## What would falsify it

- The index arm costs more tokens, or scores lower, than the source arm on a correct target.
- Answering real questions still needs the source often enough that the index is a detour.

## What would make it unfalsifiable

These are threats to validity: each one, if allowed, makes the experiment incapable of
returning a negative result.

**A lexical search tool over the index.** It returns raw lines, spends the tokens the index
exists to save, and removes the constraint that forces a structural query. The index arm becomes
the source arm with extra steps and there is no difference left to measure. A gap a `grep` would
close is a missing *layer*; the fix is to model the thing being searched for.

**Teaching to the test.** A change that adds exactly what a rubric grades contaminates that
mark. Disclose it, or the benchmark becomes a self-portrait.

**A rubric enumerated from what `grep` surfaced.** If marks are collected bottom-up from what a
lexical search found, the rubric is shaped by the source arm's way of working and the index arm
can only win by doing `grep`'s job faster. That caps the measurable effect at "a faster grep",
which is not this hypothesis. Marks are answer components derived top-down from the question.

**Self-grading.** This project writes the tool, the rubric and the judge. Source-derived ground
truth, arm fencing, declared contamination and the unanimity veto exist to bound that conflict.
They do not remove it.

## How it is measured

`acceptance/` — paired questions, both arms, several model tiers, public targets only. Read the
numbers from the committed result, never from a summary of it.

**All three axes, every time.** `total_tokens` is never quoted alone: it is a turn counter
multiplied by a mostly-cached prompt, so it tracks round trips far more closely than it tracks
anything retrieved, and the two have disagreed in SIGN on the same run. Quote it beside
`result_bytes`, or a single number can be made to say whatever the author wants.

Report grading coverage beside every score. A mark the judge never ruled on is not a miss, and
counting it as one turns flaky infrastructure into a result.

## If it holds

Use the index on every repository — first-party, third-party, vendored, gitignored. There is no
principled reason to restrict it to code you own.
