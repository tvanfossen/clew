Clew has five ways to set indexing conventions, and when they disagree the rule is simple: a stated value replaces the guesses for that option, but facts never get dropped. I answered from the index's docstrings and tests, not the source, and one entry point's file changed after the index was built, so verify details before relying on them.

**The ways to say so, from strongest to weakest**

| Tier | Source | Combines by |
|---|---|---|
| 1 | CLI flag, or the `options` argument for an embedding caller (MCP and API) | Replaces the stated layer |
| 2 | `.clew.yaml` at the repo root | Replaces the stated layer |
| 3 | Facts the repo already wrote: Doxyfile `ALIASES`/`PREDEFINED`, generator manifests, language or platform entry points | Accumulates |
| 4 | Known-ecosystem signatures (e.g. UDM, ingot) | Accumulates |
| 5 | Built-in name-pattern heuristics | Replaced by any stated tier |

- `.clew.yaml` sections are named after the option they set (`shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `index_scope`, `doxyfile`, `kconfig`, `preprocessor`, and others). Each section holds the same content as the standalone manifest file.
- Unknown top-level keys are refused by name. Keys with an experimental prefix are tolerated and ignored, so an older clew doesn't hard-fail on them.
- `guard:` in the same file configures the doxygen gate, not the index.
- The Doxyfile's `INPUT` is no longer a scope tier (gh#333). Its `ALIASES` and `PREDEFINED` are still used, but its `INPUT` is replaced.

**When they disagree**

- **Flag vs declaration, same option:** the flag wins outright and the declaration is ignored for that option. The declaration is the standing statement; the flag is a deliberate one-off.
- **An empty flag is a withdrawal, not a statement:** `[]` or an empty inline document falls through to the declaration, then to the guesses. This lets an operator undo a recorded flag without deleting the database.
- **Declaration vs heuristic:** the declaration displaces the guesses.
- **Facts and ecosystem layers:** these accumulate under any stated tier. Tiers 3 and 4 behave identically, so arguing which one a value belongs to changes the label but not the result. Flagging `--entry-patterns` used to drop `main`; under this rule `main` survives any stated tier.
- **Restated facts:** they are not duplicated.
- **Scope:** a declared `index_scope` is the only scope decision. If it is rejected, internal callers log a warning and fall back to whole-repo scope. The CLI and MCP refresh path check first and refuse instead.
- **Malformed `.clew.yaml`:** it is ignored entirely and built-in defaults apply. The build reports that the file was ignored.
- **Recording:** the winning tier is stored in `build_meta`. Only tier-1 statements are replayed on refresh, and a withdrawn statement is not replayed from a stale row.

I did not confirm how the CLI resolves a scope flag against a declared `index_scope`, since that lives in `clew/scope.py` and `clew/cli.py`, which the index only described.