## What determines the AIRD number

`calculate_aird` (src/complexity.rs:1433) is a pure function of six pre-computed metrics, each derived by walking the function's own AST — nothing external, nothing timing-based:

```
cognitive_norm = min(cognitive/75, 1.0)
sloc_norm      = min(sloc/200,     1.0)
nesting_norm   = min(nesting/8,    1.0)
test_norm      = min(max(test_score,0)/20, 1.0)
doc_norm       = min(max(doc_score,0)/10,  1.0)
coupling_norm  = min(state_coupling/12,    1.0)

raw = 55*cognitive_norm + 15*sloc_norm + 15*nesting_norm + 15*test_norm
      - 15*doc_norm + 10*coupling_norm

AIRD = round(raw).clamp(0, 100)
```

So: **Cognitive complexity is the dominant driver (weight 55)**, SLOC/nesting/testability each contribute up to 15, documentation *subtracts* up to 15, and state coupling to the function's own struct/class adds up to 10. All six inputs (`cognitive`, `sloc`, `nesting`, `test_scoring.total_score`, `test_scoring.documentation_score`, `state_coupling`) come from `calculate_cognitive_complexity`, `calculate_sloc*`, `calculate_nesting_depth`, `calculate_test_scoring`, `calculate_state_coupling` — all pure tree-sitter traversals over the node, called once per function in `collect_function_metrics` (src/lib.rs:891).

There's a second, separate mechanism layered on top: `apply_aird_ce_multiplier`/`aird_file_ce_multiplier` re-scale an already-computed AIRD by the *file's* efferent coupling (Ce) — a corpus-wide import-graph metric — up to a 20% bump, capped and re-clamped to 0–100. This is meant to run as a post-pass (`apply_file_ce_to_aird` in src/coupling.rs) once the whole corpus's import graph is known, since a single function's own AIRD is computed "eagerly," before any other file exists.

One thing worth flagging honestly: **the index shows zero callers anywhere for `apply_file_ce_to_aird`.** `collect_all_metrics` (src/main.rs, the multi-file/matrix/SARIF entry points) calls `collect_function_metrics` directly and never touches `coupling::apply_file_ce_to_aird` or constructs `FileCoupling`. `FunctionMetrics.file_ce` is hardcoded to `0` at construction and nothing in the indexed call graph overwrites it. So as far as static call resolution can tell, the Ce-multiplier path is present in the codebase but currently unwired into any of the four run modes — I can't rule out a dynamic/feature-gated call the AST resolver misses, but on the evidence available this looks like dead code, not an active part of the score.

## Same function, two runs — same score?

Given that finding, yes: since the Ce-multiplier post-pass appears unreachable, AIRD reduces to the pure per-function formula above, and every input is deterministic — same source AST in, same integers out, no randomness, no global/mutable state, no wall-clock or ordering dependency. `collect_all_metrics` does process files in parallel via `rayon`, but each file's metrics are computed independently and the result is deterministically re-sorted by `(file_path, name)` afterward, so parallelism doesn't perturb any individual function's score.

Caveat, and it's the one that actually matters: **if `apply_file_ce_to_aird` ever does get wired in** (a code path the index doesn't show me, or a future change), then AIRD would stop being a pure per-function property — it would depend on which other files are analyzed alongside it in that run, since file-level Ce comes from the corpus-wide import graph. The same function could then score differently between a single-file run and a `--recursive` corpus run, or between two recursive runs over different file sets. That's a scope-dependent source of variation the current (apparently dead) code was clearly designed to introduce, so it's worth watching for if this changes.
