The repository has four ways to state indexing conventions, plus two built-in layers that apply when nothing is stated. When two statements disagree, the rule depends on the option. Stated values usually replace the built-in guesses. Facts written by the target and ecosystem signatures always accumulate.

**Ways to say so, highest precedence first**

| Tier | Source | Behaviour |
|---|---|---|
| 1 | CLI flags (`--shared-key-patterns`, `--exclude`, `--doxyfile`, …), or the `options` argument for an embedding caller such as the MCP server | Replaces the lower stated layers for that option. |
| 2 | `.clew.yaml` at the repo root, one section per convention (`index_scope:`, `shared_key_patterns:`, `thread_patterns:`, `mqtt_dispatch:`, `doxyfile:`, `kconfig:`, …) | Replaces the guesses. |
| 3 | Facts the target already wrote, such as a Doxyfile's `ALIASES` and `PREDEFINED` | Accumulates. |
| 4 | Known-ecosystem signatures | Accumulates. |
| 5 | Name-pattern heuristics | The floor. Any stated tier displaces it. |

Notes on the sources:
- The `options` argument uses the same vocabulary as `.clew.yaml`, and every declaration section can be stated that way. The one exception is `predefined`, kept as a documented alias for `preprocessor.predefined`.
- The repo's own Doxyfile is still used for `ALIASES` and `PREDEFINED`, but its `INPUT` no longer decides the index scope.
- `--scope`, `--index-cache` and `--rebuild` are per-run mechanics, not declarations, so they have no section.
- The `guard:` section of `.clew.yaml` configures the doxygen gate, not the index. Index declarations and gate config share the file but not the keys.
- `clew propose` drafts a commented `.clew.yaml` and dry-runs each candidate against the index, rejecting any that do not pay off. `clew export` writes stated tier-1 statements back out as a declaration.

**When two disagree**

- **Flag against declaration:** the explicit flag wins outright and the declaration is ignored for that option. Replacing options work this way, and the test `test_tier_one_beats_tier_two` covers it. Nothing is reported as a conflict.
- **Declaration against heuristic:** the declaration wins and the heuristic is discarded. The test `test_a_declaration_displaces_the_guesses_and_keeps_the_facts` covers this case.
- **Facts and ecosystem signatures:** these never lose to a stated tier. They are unioned with whatever is stated, so a `--entry-patterns` flag cannot drop `main`.
- **An empty explicit list** (`[]`) is a withdrawal, not a statement. It falls through to the declaration and then to the guesses.
- **Which tier won** is recorded in `build_meta`. A tier-1 statement is also recorded for replay, but a declaration is re-read from the file rather than replayed from a frozen copy.
- **Partial options:** `apply_options` validates the whole mapping before assigning anything. One bad entry rejects the lot rather than applying half of it.

**Scope is the exception to "the declaration is advisory"**

`index_scope` is the only source that yields index roots. If it is rejected, for example because no declared root exists, `derive_scope` logs a warning and falls back to the whole repository. The CLI and MCP refresh paths call `declared_scope_rejection` first and refuse the build instead. The test `test_cli_apply_scope_refuses_a_rejected_declaration` covers this. An excludes-only `.clew.yaml` once let a build run into a vendored tree its own declaration was trying to keep out, which is why the refusal exists.

One caveat: the indexed body of `resolve_layered` no longer matches its source line range, so I read its logic from the docstring and the test names rather than the current code.