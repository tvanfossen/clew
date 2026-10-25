<!-- SPDX-License-Identifier: MIT -->
# Pre-registration — does formalized usage guidance change how the index gets used?

**Written before `SKILLS.md` existed.** Git history shows this commit preceding it. A prediction
written after seeing the thing it predicts is not a prediction.

## The question

The 1.1.0 baseline (`acceptance/runs/2026-10-19-n3`) measured, over 30 cells:

| | measured |
|---|---|
| dossier calls passing a SINGLE subject | **245 of 353 — 69%** |
| dossier calls using `depth > 1` | **10 of 353 — 3%** |
| `index_only` turns vs baseline | **+11.8%** |
| `index_only` output tokens vs baseline | **-29.8%** |

`dossier` accepts up to eight subjects per call and `depth` walks the causal graph in one call
instead of N. Both are documented in the tool description and both are largely unused. The
served `INSTRUCTIONS` describe them rather than directing their use.

So: **does a formal usage document reduce round trips?**

## The design — BEFORE/AFTER ON ONE ARM, not an arm comparison

The obvious experiment is wrong. Giving the index arms a usage document while `baseline` gets
nothing makes one arm coached and the other not — the brief asymmetry that invalidated the first
mbedtls run and that `check_symmetry` exists to prevent.

Instead each index arm is compared **against itself**:

    index_only WITH SKILLS.md   vs   index_only WITHOUT   (the 30 baseline cells already frozen)
    index      WITH SKILLS.md   vs   index      WITHOUT

Same questions, same rubric digest, same targets, same model, same seed. The ONLY difference is
the document. `baseline` is not re-run and is not part of this comparison.

n=1 per (question, arm), entropic + mbedtls, 2 arms = **20 cells**.

## The prediction, fixed now

**PRIMARY — mechanical counts, where n=1 is adequate because these are counts and not judgements:**

1. `index_only` **turns go DOWN** versus the same arm without the document.
2. `index_only` **output tokens go DOWN or hold** (they are already -29.8% against baseline;
   fewer round trips should not cost more output).
3. The share of dossier calls passing **more than one subject RISES above 31%**.
4. The share using **`depth > 1` RISES above 3%**.

**SECONDARY — reported, not concluded from:**

5. Quality. The noise floor is unmeasured and n=1 cannot separate a few points from nothing.

## What the document CANNOT fix, stated in advance so a null result is read correctly

Of the 11 marks `index_only` loses 3/3 to baseline on the 1.1.0 baseline:

| cause | marks | reachable by documentation? |
|---|---:|---|
| files outside the indexed set — `scripts/generate_errors.pl` has **0 path rows**, Perl is not among the 21 grammars | 4 | **no** |
| negative space — a default that FAILS, a default-ALLOW posture | 2 | **no** |
| tree-wide aggregation the index holds the data for | 3 | **plausibly** |
| threads-detector gap — a spawn whose lambda has no single named entry | 1 | **no** |

So the realistic quality ceiling is the three aggregation marks. **A document cannot close a
17.9pt gap whose majority is content the index does not hold**, and nobody should read it as
trying to. Owner's own framing, 2026-10-20: *"I dont expect the index to be able to find things
it fundamentally doesnt index."*

## Stopping rule

**ONE round.** Whatever this shows is published. If the document fails to move turns, that is
the result — the document does not get rewritten and re-measured until it passes, because
measure → dislike → adjust is how a benchmark becomes a self-portrait, and this project has
already caught itself doing it once.

## Disclosure that travels with any later number

`SKILLS.md` and the served `INSTRUCTIONS` are part of the PRODUCT. A future run showing better
turns is therefore measuring the documentation plus the index, not the index alone. That is a
legitimate product improvement and it must be disclosed as a change between baselines — exactly
as the brief asymmetry was — rather than folded into "the index got better."
