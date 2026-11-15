Clew has five ways to say how a repository should be indexed. They stack in a fixed order, and when two disagree the higher tier wins, but only for the values it actually states. Facts and ecosystem signatures never get removed by anyone.

**The five tiers** (from `clew/tiers.py`, the module docstring and `resolve_layered`):

| Tier | Source | How it combines |
|---|---|---|
| 1 explicit | CLI flag, or the `options` argument for embedding callers and MCP | Replaces the stated layer |
| 2 declared | `.clew.yaml` at the repo root | Replaces the stated layer |
| 3 target-fact | Facts the repo already wrote: Doxyfile `ALIASES`/`PREDEFINED`, generator manifests, language entry points | Accumulates |
| 4 ecosystem | Known-ecosystem signatures (UDM, ingot) | Accumulates |
| 5 heuristic | Name-pattern guesses, the floor | Replaces the stated layer |

**What the ways are for:**

- **CLI flags** cover one-off runs, like `--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--data-model`, `--entry-patterns`, `--extra-input`, and `--doxyfile`. Run mechanics such as `--scope`, `--index-cache` and `--rebuild` are deliberately not declarations, because they describe one run rather than the repository.
- **`options`** is the structured argument that gives MCP and embedding callers the same reach as flags. Its vocabulary is the `.clew.yaml` section names, and the module says every declaration section is statable this way.
- **`.clew.yaml`** is the standing statement, and the one that matters most for MCP. Each section holds the same content as the standalone manifest it replaces. `predefined` is kept as an alias for `preprocessor.predefined`.
- **The repo's Doxyfile** is discovered by name in the root, `docs/` or `doc/`. It contributes `ALIASES` and `PREDEFINED` as facts. Its `INPUT`, `EXCLUDE*` and `FILE_PATTERNS` do not decide what gets indexed. Index scope comes from the declaration's `index_scope`, and otherwise defaults to the whole repo. A stated `doxyfile` path must exist, or the build refuses rather than silently falling back.

**When two disagree:**

1. **Flag or `options` beats `.clew.yaml`, which beats the heuristic floor, for the same list-valued option.** The winning stated layer replaces the guesses. Tiers 3 and 4 survive every stated tier, so a `--entry-patterns` flag cannot drop `main`. That was a real bug the design was built to prevent.
2. **For a whole-document option such as `shared_key_patterns`, the stated document replaces the declaration entirely.** It is not merged. The test `test_a_stated_document_beats_the_declaration_and_reaches_the_loader` shows the declared writer `FROM_DECL_` disappearing once a stated document names `STATED_`.
3. **An empty value is a withdrawal, not a statement.** An empty list or `{}` falls through to the next tier, so it can undo an earlier flag without deleting the database.
4. **The winner is recorded.** The stored build metadata names which tier supplied each option, and `index(action='status')` reports the options an operator stated. A stated flag is replayed on later builds, and a declared file is re-read rather than replayed.

**Caveats:** Some of the bodies I read were flagged `anchor_mismatch`, so line numbers may be stale; I relied on the index's verbatim bodies and the docs rather than re-reading the parser. I did not verify the legacy-config warning path in detail.