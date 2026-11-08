Clew has three ways to tell it about a repository, plus a fourth that only proposes text. When they disagree, the explicit statement wins, but the stated layer replaces only the guesses, never the facts.

**The ways to say so**

1. **CLI flags** (tier 1, "explicit"). Flags such as `--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--data-model`, `--doxyfile`, `--entry-patterns`. A flag is a deliberate one-off override.
2. **`options` argument** (also tier 1). Embedding callers, including the MCP `index` tool, pass one structured `options` mapping to `index(action='refresh')`. Its keys are the same section names as the declaration file, and an unknown key is refused by name. Before this, MCP callers could not state tier 1 at all.
3. **`.clew.yaml` in the repo root** (tier 2, "declared"). Each section holds the same content as the standalone manifest, so a flag's contents can be moved in verbatim. The `guard:` section belongs to the doxygen gate and is dropped before the index reads the file. Sections include `shared_key`, `threads`, `mqtt`, `data_model`, `entry_patterns`, `test_paths`, `requirements`, `index_scope`, `doxyfile`, `preprocessor`, `kconfig`, `vendored`, `sub_indexes` and `enrich`.
4. **Facts the target already contains** (tier 3, "target-fact"). Examples are a Doxyfile's ALIASES and PREDEFINED, a generator manifest, or a language or platform entry point. These are read from the repo, not stated by anyone.
5. **Ecosystem signatures** (tier 4) and **name-pattern heuristics** (tier 5). These are built-in defaults. Clew can also propose a starter `.clew.yaml` via `propose_declaration`, but the proposal is written entirely as comments and changes nothing until a human copies it in.

**When they disagree**

The rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. Clew's own summary is "you can correct our guesses; you cannot un-discover a fact."

- **Tier 1 beats tier 2.** A CLI flag or `options` value replaces the declared value for that option. The file is the standing statement and the flag is the one-off override.
- **A stated tier (1 or 2) replaces the heuristics (tier 5).** The guesses are discarded.
- **Tiers 3 and 4 always accumulate.** No stated value removes a fact the repo itself provides, so a declaration cannot delete a Doxyfile-derived fact.
- **An empty explicit list is a withdrawal, not a statement.** `[]` falls through to the declaration and then to the guesses. This is how a recorded flag is undone without deleting the database.
- **The winning tier is recorded in `build_meta`.** Only a tier-1 statement is recorded for replay, so a later rebuild reproduces it.

The motivating bug: `--entry-patterns` used to replace the defaults, so passing it dropped `main` and reachability collapsed without any report. Under the current rule a stated value cannot drop `main`.

**Other rules that affect disagreement**

- **Validation is all-or-nothing.** `apply_options` validates every entry before it assigns any, so one bad entry leaves the build untouched.
- **Unknown sections in `.clew.yaml` are refused.** A misspelled section would otherwise run on defaults while reporting the declaration as honoured. Sections prefixed `experimental_` are tolerated and ignored, with a warning.
- **Malformed YAML is not refused.** It is logged at WARNING and treated as absent, so the build falls back to defaults.
- **Discovery is limited to the repo root.** Sub-index declarations are read only from the root, so a nested `.clew.yaml` is never read.

**Caveat:** the index does not expose a per-option conflict report. You learn which tier won from `build_meta` and the logs. I did not confirm the exact log wording for a tier-1 versus tier-2 override.