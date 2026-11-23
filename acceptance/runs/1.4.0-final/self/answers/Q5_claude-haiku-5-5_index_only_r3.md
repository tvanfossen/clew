The index has four ways to say what to index, and they don't all combine the same way. Declarations and explicit values replace the guesses, but facts that someone else already wrote accumulate and are never discarded.

**The ways to say so**

1. **Tier 1, explicit:** a value stated at call time, such as a CLI flag or an option passed through the MCP `build_or_refresh` / `build_index` calls. `buildoptions.py` documents this as the top tier, and it is the only tier an MCP caller can reach. Its per-run mechanics (`--scope`, `--index-cache`, `--rebuild`) are not declarations and have no `.clew.yaml` section.
2. **Tier 2, declared:** the repository's `.clew.yaml`. Its `index_scope:` key is the only tier in `scope.py` that is a decision about the index. Its other sections (including `doxyfile:`, `kconfig:` and the `guard:` section) are documented in `buildoptions.py` and `docs/GUARD.md`.
3. **Tier 3, target-fact:** facts the repository already wrote, such as a Doxyfile's `ALIASES` and `PREDEFINED`, a generator manifest, or a language or platform entry point. The Doxyfile is still read for these, but its `INPUT`, `EXCLUDE*` and `FILE_PATTERNS` no longer set scope (gh#333). The reason is that a Doxyfile's `INPUT` is a documentation target, not a reasoning boundary; honouring it would have made a repo that documents itself get a smaller index.
4. **Tier 4, ecosystem:** a known-ecosystem signature (UDM, ingot).
5. **Tier 5, heuristic:** name-pattern guesses, the floor, explicitly provisional.

Scope itself has two tiers: the declared `index_scope:`, and otherwise the whole repository minus what git ignores. Nested git trees are indexed and tagged, not excluded.

**When two of them disagree**

`tiers.py` defines one rule: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **Stated tiers displace guesses.** A flag beats a declaration, and a declaration beats heuristics. The highest stated tier present wins, and it is recorded in `build_meta` so the winning tier is visible and replayable.
- **Facts and ecosystem signatures always survive.** Tiers 3 and 4 accumulate under every stated tier. You can correct a guess; you cannot un-discover a fact.
- **An empty explicit list is a withdrawal, not a statement.** `[]` falls through to the declaration and then to the guesses. That lets an operator undo a recorded flag without deleting the database.
- **Scope has no conflict between Doxyfile and declaration.** Since gh#333 the Doxyfile does not set scope at all, so `index_scope:` is the only decision.

The motivating bug explains the design: passing `--entry-patterns` once replaced the default entry points, so `main` dropped out and reachability collapsed with no report. Under the current rule a stated value cannot remove a fact-derived entry.

Caveat: the `resolve_layered` body was flagged as an anchor mismatch, so its line numbers may be stale. The rule itself matches the module documentation.