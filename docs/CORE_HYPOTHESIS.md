<!-- SPDX-License-Identifier: MIT -->

# Core hypothesis

**An agent answering questions about a codebase from a queryable index of its enforced
documentation spends fewer tokens and gives better answers than one reading the source.**

## If it holds

Use the index on every repository — first-party, third-party, vendored, gitignored. There is
no principled reason to restrict it to code you own.

## What has to be true

**Richness.** A thin database cannot replace reading source, and the thinner it is the weaker
the case for replacement. Every question a developer actually asks that the index cannot
answer is a reason to reach for `grep` instead — and a good one.

**A different shape of question.** The index does not answer lexical questions ("which files
contain this string"). It answers structural ones ("who calls this", "what implements this
requirement", "what reaches this across a thread boundary"). Learning to ask the second kind
is part of the claim, not a workaround for it.

## What would falsify it

- The index arm costs more tokens, or scores lower, than the source arm on a correct target.
- Answering real questions still needs the source often enough that the index is a detour.

## What would make it unfalsifiable

**A lexical search tool over the index.** It returns raw lines, spends the tokens the index
exists to save, and removes the constraint that forces a structural query. The index arm
becomes the source arm with extra steps and there is no difference left to measure. A gap a
`grep` would close is a missing *layer*; the fix is to model the thing being searched for.

**Teaching to the test.** A change that adds exactly what a rubric grades contaminates that
mark. Disclose it, or the benchmark becomes a self-portrait.

## How it is measured

`acceptance/` — paired questions, both arms, several model tiers, public targets only. Read
the numbers from the committed result, never from a summary of it.

**Four axes, always all four: round trips, retrieved bytes, time, completeness.** Report the one
that hurts first.

`total_tokens` is not one of them on its own. It is a turn counter multiplied by a mostly-cached
prompt, so it tracks round trips far more closely than it tracks anything retrieved — and the two
have disagreed in SIGN on the same run. Quote both, or a single number can be made to say
whatever the author wants.

Report grading coverage beside every score. A mark the judge never ruled on is not a miss, and
counting it as one turns flaky infrastructure into a result.
