There are four ways to say how clew should index a repo, plus the defaults. When they disagree, the rule depends on whether the option is a single value or an accumulating list.

**The ways to say so**

| Tier | Source | How it combines |
|---|---|---|
| 5 | Built-in name-pattern heuristics (the floor) | Replaced by any stated tier |
| 4 | Known-ecosystem signatures (e.g. UDM, ingot) | Accumulates |
| 3 | Facts the target already wrote: Doxyfile `INPUT`/`EXCLUDE`/`FILE_PATTERNS`/`ALIASES`/`PREDEFINED`, generator manifests, language or platform entry points | Accumulates |
| 2 | `.clew.yaml` at the repo root (14 sections, same format as the standalone manifest files) | Replaces tiers 5 and 4-stated values |
| 1 | CLI flags, or the `options` argument for embedding callers | Replaces the stated layer |

The `.clew.yaml` file is the in-tree route. Because both the CLI and MCP find it from the repo root, it is the only option that reaches MCP callers without per-flag plumbing. The old `.doxygen-guard.yaml` is a hard break and is no longer read. The `guard:` section of `.clew.yaml` configures the gate, not the index.

**When they disagree**

- **Single-valued options (tier 1 and 2 vs tier 5):** the stated layer replaces the guesses. Within stated layers, a CLI flag beats the declaration. The flag is treated as a deliberate one-off override, and this is tested in `test_explicit_flag_wins_over_the_declaration`.
- **Accumulating options (tiers 3 and 4):** nothing is replaced. A Doxyfile's `PREDEFINED` and a declared `preprocessor.predefined` union together. A disagreement here only changes labels, not the resolved set.
- **An empty explicit list** (`[]`) is a withdrawal, not a statement. It falls through to the declaration and then the guesses, so you can undo a recorded flag without deleting the database.
- **Declaration vs convention:** the declaration wins. The requirements catalog is the worked example. The CLI and MCP used to resolve it differently, so a repo with both a declared catalog and a conventional `requirements.yaml` got different indexes depending on the entry point. That is fixed and covered by `test_the_catalog_precedence_is_declaration_then_convention`.
- **Declaration vs Doxyfile for scope:** a test docstring says the order is declaration, then guard, then Doxyfile. I did not verify that in code.
- **Malformed `.clew.yaml`:** it is ignored entirely and built-in defaults apply. A refusal message then says so.
- **Stated paths that don't exist:** a stated Doxyfile path must exist, or the build fails. It does not silently fall back to whole-repo synthesis.

**What you don't get on a conflict**

The conflict is resolved silently. The winning tier is written to `build_meta` (and into the stamped provenance), so you can see afterwards which tier won. I did not find a warning emitted when a flag overrides a declaration.

**Index caveat**

The index is stale for `clew/tiers.py`: `resolve_layered` and `_stated_layer` report `anchor_mismatch`, and their line numbers are off by a few lines. The logic I read matches the description above. Running `index(action='refresh')` would fix the line numbers.