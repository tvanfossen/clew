## What actually determines the AIRD number

`calculate_aird` (`src/complexity.rs:1433-1456`) is a pure function of six inputs, all computed per-function from the parsed AST inside `collect_function_metrics` (`src/lib.rs:891-991`):

- `cognitive` — cognitive complexity (55% weight, the dominant term)
- `sloc` — lines of code (15%)
- `nesting` — nesting depth (15%)
- `test_score` — `test_scoring.total_score`, an iteration-cost proxy (15%)
- `doc_score` — `test_scoring.documentation_score`, subtracted (−15%, documentation lowers AIRD)
- `state_coupling` — coupling to the function's own struct/fields (10%)

Each is normalized against a fixed denominator (75, 200, 8, 20, 10, 12 respectively), capped at 1.0, weighted, summed, then `raw.round().clamp(0.0, 100.0)`. `calculate_aird_raw` is the same formula without the `.min(1.0)` caps, used only for progress-tracking output when the capped score is pinned at 100.

There's a second-pass adjustment layered on top: in `--recursive` mode, once the whole corpus's import graph is built, `apply_file_ce_to_aird` (`src/coupling.rs:162-172`) looks up each function's *file-level* efferent coupling (Ce) and calls `apply_aird_ce_multiplier`, which re-scales the already-computed AIRD by up to `1 + AIRD_FILE_CE_MAX_BONUS` (a 20% max bump, per the field brief), re-clamped to [0,100]. This is a genuinely separate signal from the function's own `state_coupling` — it captures "this file imports a lot of the corpus, so reasoning about it needs wider context" — and it is corpus-dependent: it comes from `index_ce_by_file`, a lookup keyed by `file_path` off the `FileCoupling` list computed for the whole scanned tree.

## Would the same function score the same across two runs?

Every input feeding `calculate_aird` is a pure tree-sitter traversal over the function's own source text — no I/O, no randomness, no clock, nothing environment-dependent that the index can see. So for a fixed function body, in isolation, the six base metrics and the base AIRD are deterministic and will reproduce identically.

The one thing that can change the *reported* number between runs without the function's own code changing is the Ce multiplier: it depends on the file-level import graph of whatever corpus was scanned. If run A is single-file mode (or a `--recursive` scan over a different file set than run B — e.g. a subdirectory vs. the whole repo, or files added/removed elsewhere in the tree), `file_ce` for that function's file can differ, and `apply_aird_ce_multiplier` will produce a different final AIRD even though the function's own metrics are unchanged. So: same function, same file, same corpus scope → same AIRD, deterministically. Same function scored under different invocation scope (single-file vs. recursive, or recursive over a different set of files) → the base score is stable but the Ce-adjusted final score can differ.

One gap the index can't settle from structure alone: I can't confirm from the graph whether `test_scoring`/`calculate_state_coupling` themselves have any dependence on traversal order or hashmap iteration that could be non-deterministic for pathological inputs — I only have their call relationship, not their bodies. Given the project's stated design constraint ("pure tree-sitter traversal, no I/O") in the file-level doc, I'd treat this as very unlikely, but it's a gap based on what dossier surfaced rather than a verified negative.
