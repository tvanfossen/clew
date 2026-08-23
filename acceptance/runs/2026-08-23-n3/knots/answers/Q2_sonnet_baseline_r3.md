All the per-function inputs (cognitive, sloc, nesting, test_scoring, state_coupling, external_calls) are pure, deterministic tree-sitter traversals over that function's own AST — same source text always produces the same numbers, and I don't see any non-determinism (no hashing-order dependence, no timing, no RNG) in `complexity.rs`.

**What determines the number:**

```
raw = cognitive/75 ×55        (primary driver — reasoning steps)
    + sloc/200     ×15        (context volume)
    + nesting/8    ×15        (structural confusion)
    + test_score/20×15        (iteration cost from low testability)
    − doc_score/10 ×15        (docs reduce ambiguity — the only negative term)
    + state_coupling/12 ×10   (self/struct-field coupling)

aird = round(clamp(raw, 0, 100))
```

then, **only in `--recursive` mode**, a second pass multiplies that score by up to ×1.20 based on the file's efferent coupling (`Ce`: how many other corpus files it imports), via `apply_aird_ce_multiplier` / `aird_file_ce_multiplier` — capped at `Ce = 10`.

So it's six per-function structural signals off that function's own AST (cognitive complexity, SLOC, nesting depth, a testability score, a doc-comment score, and struct-field/self-coupling), plus one corpus-level signal (the file's import fan-out) layered on afterward.

**Would you expect the same score on two different runs?**

Yes — for a fixed input, `calculate_aird` and the AST metrics feeding it are pure functions of the parsed source; there's no clock, RNG, or thread-order dependency in that path. The one place I checked for hidden non-determinism was `build_import_graph`/`FileCoupling`: `Ce` is a `HashSet<String>` cardinality, and `HashSet::len()` doesn't depend on Rust's randomized iteration order, so that count is stable run-to-run too, and `ImportGraph::coupling()` explicitly sorts its output by `file_path` before consumption.

The two things that *would* legitimately change the number between runs, though, aren't run-to-run noise — they're scope changes:

1. **`--recursive` vs. single-file invocation.** Without `--recursive`, `apply_file_ce_to_aird` never runs, `file_ce` stays 0, and the multiplier is never applied — same function, lower AIRD, run without the flag.
2. **Which files are in the corpus.** `Ce` (and thus the multiplier) depends on the full set of files passed to `build_import_graph`. Running against a subdirectory vs. the whole repo, or adding/removing a file that this file's imports resolve against, changes `Ce` even though the function itself didn't change — so "same function, same flags, same file set" is the actual determinism guarantee, not "same function" alone.
