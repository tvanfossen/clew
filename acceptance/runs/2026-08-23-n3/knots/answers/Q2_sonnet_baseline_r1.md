This is deterministic — Ce is a set cardinality (HashSet), so iteration order in the HashMap doesn't affect the resulting `ce` count. Good, that confirms determinism for the file-coupling piece too.

I have enough to answer.

## What determines AIRD

AIRD (`calculate_aird` in `src/complexity.rs:1433`) is a weighted sum of five per-function metrics, each independently normalized to 0–1 against a fixed denominator and capped, then rescaled and clamped to 0–100:

```
AIRD = min(cognitive/75, 1)·55
     + min(sloc/200,   1)·15
     + min(nesting/8,  1)·15
     + min(test_score/20, 1)·15
     − min(doc_score/10,  1)·15
     + min(state_coupling/12, 1)·10
```

- `cognitive`, `nesting`, `sloc` come straight from the tree-sitter traversal of that function's own AST (`calculate_cognitive_complexity`, `calculate_nesting_depth`, `calculate_sloc*`).
- `test_score`/`doc_score` come from `calculate_test_scoring` (testability heuristics + a doc-comment score that subtracts from the total).
- `state_coupling` comes from `calculate_state_coupling` (how much the function touches its own struct's fields / has high arity).

After that per-function score is computed, one more factor can rescale it: if you run with `--recursive`, `apply_file_ce_to_aird` (`src/coupling.rs`) multiplies the score by up to 1.20× based on the file's efferent coupling (Ce) — the number of *other corpus files* it imports, from a whole-corpus import graph built after all files are parsed. That's the only piece of the score that depends on anything outside the function itself.

## Would the same function score the same across two runs?

Yes, deterministically — assuming the same inputs:

- Every term in the formula is a pure function of the parsed AST of the source text. No randomness, no timestamps, no environment reads.
- The Ce multiplier is a `HashSet` cardinality (distinct imported files), so `HashMap`/`HashSet` iteration order in the import graph can't perturb the count — it's order-independent by construction.
- `calculate_aird_raw` and `calculate_aird` share the same deterministic formula; the only difference is capping.

What *would* change the number between "runs":
1. **The source file itself changed** (even whitespace inside the function, since SLOC/cognitive/nesting are line- and structure-sensitive).
2. **Different CLI scope** — running non-recursive vs. `--recursive`, or changing which files are included in a recursive corpus, changes the file's Ce and therefore the ×1.0–1.20 multiplier, even though the function's own code didn't change.
3. **Inline suppression comments** added/removed near the function (affects `suppressed`, not the raw score, but affects whether it's reported/gated).
4. **A different knots version** — the weights, caps, and denominators (`75`, `200`, `8`, `20`, `10`, `12`, the `0.20` Ce bonus cap) are constants calibrated in this codebase and can change release to release.

So: same source, same invocation scope, same knots version → bit-for-bit identical AIRD every time. The only way to get a different number for "the same function" is if one of those four things silently differs between runs — most commonly #2, since people often don't realize non-recursive vs. `--recursive` runs can score the same function differently via the Ce multiplier.
