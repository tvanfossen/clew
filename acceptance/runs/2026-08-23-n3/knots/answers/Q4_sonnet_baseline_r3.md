I now have everything needed.

## The two functions

`calculate_aird` (`src/complexity.rs:1433`) and `calculate_aird_raw` (`src/complexity.rs:1463`) compute the exact same weighted formula from the same six inputs (cognitive, sloc, nesting, test_score, doc_score, state_coupling):

```
(cognitive/75 × 55) + (sloc/200 × 15) + (nesting/8 × 15) + (test/20 × 15)
  - (doc/10 × 15) + (coupling/12 × 10)
```

The difference is entirely in **which terms get `.min(1.0)`-clamped before weighting**:

- `calculate_aird` clamps every normalized term to 1.0 *before* combining, and rounds/clamps the final result to an integer in `[0, 100]`. This is the score that's actually stored on `FunctionMetrics`, printed, and checked against `--aird-threshold`.
- `calculate_aird_raw` only clamps `nesting_norm`, `test_norm`, `doc_norm` (the terms whose caps rarely bind) — `cognitive_norm` and `sloc_norm` are left **unclamped**, so the returned `f64` can exceed 100 for very large functions, and it isn't rounded to an integer.

## Why the second one exists

Because `calculate_aird` clamps `cognitive/75` and `sloc/200` at 1.0, a function with cognitive complexity 300 and one with cognitive complexity 1000 both saturate to the same capped contribution — the reported AIRD score pins at 100 and *stops moving* even as you cut the function's complexity in half. If a refactor takes a monster function from cognitive 300 → 150, the gate-facing score can stay stuck at 100 the whole time, making it look like nothing happened.

`calculate_aird_raw` exists purely so `aird_tips`/`format_aird_breakdown` (in `src/output.rs`) can show a "raw AIRD (uncapped): N" number once a function is pinned at the ceiling — the uncapped value keeps decreasing as cognitive/sloc drop, giving a developer doing incremental extraction a real progress signal instead of a flat "AIRD: 100" that never budges until they cross below the normalization cap. It's a diagnostic/motivational readout, not the enforced score — the CI gate and stored `FunctionMetrics::aird` field only ever use the capped version.
