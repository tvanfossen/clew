There are three ways to say so, and they stack by a fixed rule. The one real conflict case is a flag against a declaration, and it resolves in the flag's favour.

**The three ways**

| Tier | Where it lives | Role |
|---|---|---|
| 1 (explicit) | CLI flags, or the `options` argument for embedding callers | Replaces the stated layer for that option. Also the only tier an MCP caller can reach for a build-time choice, via `buildoptions.py`. |
| 2 (declared) | `<repo>/.clew.yaml`, one section per option | Replaces the stated layer. This is the standing, in-tree statement of conventions. |
| 3–5 | Target facts, ecosystem signatures, name-pattern heuristics | Facts and ecosystem entries accumulate. Heuristics are the provisional floor that any stated tier displaces. |

The documented `.clew.yaml` sections map one-to-one onto the CLI options. Examples are `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `index_scope`, `doxyfile`, `kconfig`, and `preprocessor`. `guard:` is the exception: it configures the doxygen gate, and the index reads only its `@req` pattern and requirements mapping from it.

**When two of them disagree**

- **Flag vs. declaration, same option:** the flag wins. `resolve_layered` in `clew/tiers.py` computes `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. The winning tier is recorded in `build_meta`. An empty flag list (`[]`) is a withdrawal, so it falls through to the declaration and then the heuristics.
- **Facts are never discarded.** A stated tier only displaces the guesses. A Doxyfile's aliases or predefines survive a declaration, and so does `main` under `--entry-patterns`.
- **Declaration vs. built-in defaults:** the declaration replaces the heuristics for that option.
- **Malformed or unreadable `.clew.yaml`:** a warning is logged and the file is treated as absent. The build degrades to defaults.
- **Unknown section name:** the load refuses with `DeclarationError` and lists the allowed sections. A misspelled section would otherwise be ignored while the build reports the declaration as honoured. Keys with the experimental prefix are tolerated but ignored, with a warning.
- **Rejected `index_scope`:** the internal `derive_scope` falls back to the whole repo and logs the rejection. The build-time guard `declared_scope_rejection` is what the CLI and the MCP refresh path use to refuse instead. This is the one place where two entry points deliberately behave differently.
- **Scope is not a declaration:** `--scope`, `--index-cache` and `--rebuild` are per-run mechanics and have no `.clew.yaml` section by design. A Doxyfile's `INPUT` is no longer a scope source (gh#333); the Doxyfile is used only for aliases, predefines and filters.

Caveat: the index flagged `load_declaration_located` as anchored to a file that has since changed, so its line numbers may be stale. The semantics I quoted come from its docstring and were consistent with the rest of the index. `docs/GUARD.md`, `docs/languages/C_INTEGRATION.md` and the `clew/tiers.py` docstring are the authoritative prose if you want to check the details against the source.