I have the answer now — both functions and their exact use sites (`format_aird_breakdown`/`aird_tips` in `src/output.rs`).

Both functions compute the exact same weighted-sum formula:

```
raw = cognitive_norm*55 + sloc_norm*15 + nesting_norm*15 + test_norm*15 - doc_norm*15 + coupling_norm*10
```

**`calculate_aird`** (`src/complexity.rs:1433`) is the score actually stored on `FunctionMetrics.aird` and used everywhere — CLI output, JSON/CSV export, `--aird-threshold` gating, baselines. It clamps each of `cognitive_norm`, `sloc_norm`, etc. to `.min(1.0)` *before* weighting, then clamps the final result to `[0, 100]`. That's the metric knots reports and gates commits on.

**`calculate_aird_raw`** (`src/complexity.rs:1463`) uses the identical formula and identical weights, but does **not** cap `cognitive_norm` or `sloc_norm` at 1.0 before multiplying — only `nesting_norm`, `test_norm`, and `doc_norm` stay clamped (the comment on nesting is explicit: "nesting rarely exceeds cap; keep clamped"). It returns an uncapped `f64` instead of a `u32` clamped to 100.

**Why the second one exists:** once `cognitive` or `sloc` blows past its normalization denominator (75 and 200 respectively), `calculate_aird` pins at 100 and *stays* at 100 no matter how much worse the function gets — a 400-cognitive function and a 1000-cognitive function both report AIRD 100. That's fine as a CI gate (it should fail either way), but useless as a refactoring signal: if someone is hacking away at a monster function that's already over both caps, the capped score can't tell them whether their first extraction helped at all. `calculate_aird_raw` keeps climbing past 100 (e.g. it can report 300 for an extreme case), so comparing `raw_before` vs `raw_after` across refactoring steps shows real progress even while the gated `aird` score is stuck at the ceiling. This is exactly what `output.rs`'s `raw_aird_suffix`/`aird_tips` use it for — printing `raw AIRD (uncapped): N` as a supplementary progress metric alongside the capped score that triggers threshold violations, and the tests at `complexity.rs:2035` and `2050` (`test_aird_raw_exceeds_capped_for_large_inputs`, `test_aird_raw_tracks_progress_above_cap`) pin exactly this behavior.
