## What determines a function's AIRD score

AIRD ("AI Reasoning Difficulty") is a weighted composite computed in `calculate_aird` (`src/complexity.rs:1433`), fed six pre-computed metrics for that function:

```
raw = cognitive/75 × 55
    + sloc/200     × 15
    + nesting/8    × 15
    + test_score/20 × 15
    − doc_score/10  × 15
    + state_coupling/12 × 10

AIRD = round(clamp(raw, 0, 100))
```

Each ratio is capped at 1.0 before being weighted (so cognitive can't dominate past its 55-point ceiling, etc.), and there's a separate uncapped variant (`calculate_aird_raw`) used only to show refactoring progress once a function is pinned at the 100 ceiling.

The six inputs themselves come from pure tree-sitter traversals over the function's own AST node, computed once in `lib.rs::collect_function_metrics` (~line 908-949):

- **cognitive** — cognitive-complexity walk of the function body
- **sloc** — source lines of code (language-specific comment stripping, minus nested-function lines)
- **nesting** — max nesting depth
- **test_score / doc_score** — from `calculate_test_scoring` (testability heuristics + doc-comment detection)
- **state_coupling** — `calculate_state_coupling`, roughly how many of the enclosing struct's own fields the function touches

Then, only in `--recursive` mode, there's a second pass: `coupling::apply_file_ce_to_aird` computes each file's efferent coupling (Ce — how many other corpus files it imports, resolved by best-effort stem-matching in `build_import_graph`) across the **whole corpus**, and `apply_aird_ce_multiplier` re-scales the already-computed AIRD by up to ×1.20 based on that file-level Ce, re-clamping to 100.

## Would the same function score the same on two runs?

**Yes — deterministically, as long as three things hold:**

1. **The function's own source text is unchanged** — every one of the six per-function inputs is a pure function of that function's AST, no I/O, no randomness, no hashing-order dependence (state_coupling counts a `HashSet`-style field set, but the metric is a count, not an iteration-order-dependent value).
2. **The knots version/formula is unchanged** — the weights and caps are hardcoded constants; a `knots` version bump that recalibrates them (the doc comment explicitly says they're "calibrated against corpus percentile analysis") would move the score without the function changing at all.
3. **If run with `--recursive`, the surrounding corpus is unchanged** — the file-level Ce multiplier depends on the *other files present* in the same run (their imports into/out of this function's file). Move the file into a different corpus, add/remove sibling files, or run it standalone vs. `--recursive`, and the same function's AIRD can shift by up to 20%, purely from that multiplier — even though the function's own code, and the base AIRD before the multiplier, are identical.

So: same file content + same knots version + same corpus scope (or non-recursive mode) → bit-for-bit same score, every time, because nothing in the pipeline is a source of run-to-run variance (no threading races affecting order-sensitive computation, no clock/random inputs). The one axis that can legitimately produce a different number for an unchanged function is the recursive Ce multiplier, since it's corpus-relative rather than purely local to the function.
