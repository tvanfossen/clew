**Short answer:** the caller list is a list of *caller functions with provenance and confidence attached*, not a list of call sites. Reading it as the second thing is wrong in several ways.

**What's in the answer**

I queried `git_env` (depth 1). Its `callers` entries have:

| Field | Example from `git_env` |
|---|---|
| `name` | `_default_run_command`, `tracked_files`, … (6 entries) |
| `source` | `ast` (tree-sitter) or `doxygen_sqlite` |
| `confidence` | `resolved`, `exact`, `medium` |
| `edge_class` | `call` |
| `callers_unresolved` | `1` |

It also returns `callees`, `reads`/`writes`, `threads`, `requirements`, `covering_tests`, and at depth ≥2 a bounded `chain`. Each caller is a function name. No line numbers come back for individual call sites, so you need `file:line` from the body or a source read.

**Why it's not a plain list of call sites**

1. **The entries are functions, not sites.** A function that calls `git_env` twice appears once. The line numbers are missing.
2. **The count can be incomplete.** `callers_unresolved: 1` means one call site couldn't be mapped to an indexed function, so that caller is absent from the list. A `callees` list can be empty for the same reason, with the calls moved to `external_callees`.
3. **Sources differ in trustworthiness.** `ast` edges come from parsing. `doxygen_sqlite` edges come from doxygen, which emits known false self-edges. The repo has a whole guard for this: `_self_edge_callers` (`clew/call_edges.py:2198`) selects them, and `prune_fabricated_self_edges` removes them. A test docstring says that in a C++ codebase, 442 of 458 self-edge rows were anonymous-namespace functions that never call themselves, and in clew 21 of 70 were `main()` called from an `if __name__` guard. So a caller list can contain a function "calling itself" that never did, or lose a real self-call that the guard pruned. The answer is post-guard, so the raw doxygen rows are not in it.
4. **Callers are not reachability.** `git_env` also has a `threads` entry: `_first_build_worker` is spawned via `ast_spawn` at `confidence: medium`. The function runs on that thread, but no direct caller row shows it. Transitive reach needs `depth ≥ 2` with `direction: back`, and it is bounded by `max_depth` and `max_neighbors` (default 8).
5. **Coverage links need checking.** `git_env` lists `covering_tests: ["test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path"]`. The name does not obviously relate to git environment handling. I did not verify it, but I would not treat that link as evidence the code is tested.
6. **Dispatch and external callers are not visible.** Calls through function pointers, callbacks, subprocess or other languages, and anything outside the indexed file set are not in `callers` unless doxygen or the AST resolved them.

**How to use it:** treat `callers` as a navigation aid. Use it to find candidate callers, then read the call sites in source to confirm them, and check `callers_unresolved` before concluding nothing else calls the function.

I checked only three symbols (`_default_run_command`, `_self_edge_callers`, `git_env`), so these observations are about this index's answers for those symbols, not a full audit of clew's call graph.