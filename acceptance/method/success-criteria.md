<!-- SPDX-License-Identifier: MIT -->
# What clew has to prove

## Scope

**IN SCOPE — does the index improve FRONTIER model performance and token spend?** Three model
tiers (haiku / sonnet / opus), each with and without the MCP server, on the same questions and
the same targets.

The sharpest form is a TIER CROSSING rather than a within-model comparison: **does
`haiku + index` reach or beat `sonnet` or `opus` without it?** Report both.

**OUT OF SCOPE — local-model parity.** Whether a local ~4B MoE-active model with this tool can
match Haiku, Sonnet or Opus on the read/digest path is the eventual prize and is NOT measured
here. This run's silence is not a negative result.

**Release gate:** hypothesis verified AND owner-vetted is a 1.0.0 release and a directive for
wider adoption. Until then no specific improvement claim ships.

**The bar:** two of the first three metrics must IMPROVE, the third at PARITY minimum.

## The four metrics

| # | metric | direction | why |
|---|---|---|---|
| 1 | **Answer quality** vs the rubric | must improve | The only one that matters alone. Cheap fast wrong answers are worthless. |
| 2 | **Tokens consumed** | must improve (lower) | The index should answer without pulling whole files into context. |
| 3 | **Wall time to answer** | parity minimum | A slower tool will not be reached for. |
| 4 | **Regeneration latency after an edit** | low enough to be invisible | Without it the tool is read-only and an agent falls back to `grep`. |

## Tokens are the unit. Dollars are a conversion, applied afterwards if at all

A dollar figure is a token count against a price sheet, so recording dollars adds a dependency on
prices that change and a stale multiplier goes wrong silently.

- **Metric 2 is WITHIN-model** — index arm against source arm, same model, same question. Token
  counts are exactly comparable. No normalisation.
- **Only the TIER-CROSSING claim spans models**, and a Haiku token is not an Opus token. State it
  without collapsing the axes: *"haiku + index scored X% using N tokens; sonnet raw scored Y%
  using M tokens."* A reader applies their own prices.

`claude -p` reports `total_cost_usd` per cell and the harness records it. It is not the unit any
claim is stated in. On a subscription the binding constraint is session CAPACITY, measured in
tokens.

## Stating metric 2

Report **tokens consumed as a fraction of the raw-arm baseline**. Write "the index consumed
**0.52×** the tokens", never "1.9× cheaper" — the second inverts the intuition and reads as
*more*.

**No measured figure belongs in this file.** A number written into the criteria becomes the
expected answer for every target that follows. Measured values live in the target's result
document.

## Tokens and time survive a rubric change; quality does not

Metrics 2 and 3 measure what a cell COST, so they compare across runs regardless of the grading
key. Metric 1 measures what a cell was ASKED, so quality is comparable only against another run
of the same rubric. **Never print a quality delta across a rubric change.**

## Bringup is the index arm's own cost

Building or refreshing the index before a session can answer anything is a cost the source arm
never pays. Charged to the index arm, reported on its own line with its own median and range,
**excluded from the per-question figures**. The source arm gets no placeholder — a counterpart
invented for symmetry would be a fabricated measurement.

## Metric 4

**How to measure:** edit one file, refresh the index, query the changed symbol, record wall time
from edit to queryable. Report per target alongside that target's indexed-file count, because it
scales with repository size.

Two parts, and only the first is measurable today:

  a. **latency** — how long a rebuild takes after an edit
  b. **automaticity** — whether it happens without the agent choosing to spend the time
     (**does not exist**)

Latency is not the real defect; the TRIGGER is. Time spent in the background on save is
invisible. The same time an agent must decide to spend is friction, and friction loses to `grep`.

### The mutating question

Every rubric carries exactly one: make a targeted edit to the target repo, bring the answering
view up to date, and answer something that can ONLY be answered correctly from the post-edit
state. Latency is metric 4; the answer's correctness checks that the arm saw the edit.

The raw arm gets the edit for free, so this is where the index arm can structurally LOSE — which
is why it belongs. A rubric that only asks questions the index wins is a self-portrait.

**No ordering rule.** Editing mid-session is what a real user does, and within the cell the
mutation IS the question. The defect is cross-CELL leakage, and reordering does not fix it: at
n=3, run 2 inherits run 1's edit wherever the question sits. The fix is isolation — every cell
starts from the pinned state, tree AND index. Put the mutating question wherever it reads best.

## Report per target, never averaged

Every metric varies with repo size and language, so a single-target result proves nothing about
generality. A target is added by cloning it, writing a `questions.md` and an `evidence.md`, and
registering it — nothing in `acceptance/method/` or `acceptance/bench/` changes when one is.

## Evidence requirements

1. **Run data is committed beside the result**, so it can serve as a golden reference.
2. **Every mark carries a citation** a human can check: what was asked, what the ground truth is,
   and where it was measured. That is what `evidence.md` is for.
3. **No release claim of a specific improvement until the owner confirms** the grading and the run.
