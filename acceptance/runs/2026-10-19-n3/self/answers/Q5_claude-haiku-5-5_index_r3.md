Clew takes a repository's indexing choices from five places, in this order of precedence:

1. **CLI flags** (tier 1), such as `--entry-patterns`, `--doxyfile`, `--scope`, `--requirements`. These are one-off overrides for a single build.
2. **`.clew.yaml` at the repo root** (tier 2). This is the standing declaration. It has a section per option (`shared_key_patterns`, `thread_patterns`, `entry_patterns`, `locks`, `dispatch`, `vendored`, `sub_indexes`, `requirements`, `doxyfile`, and others). `clew/declaration.py` (`KNOWN_SECTIONS`) lists them all. The `guard:` section belongs to the doxygen-guard gate, and the index never reads it.
3. **MCP `options` argument** (tier 1 for embedding callers). The MCP server takes the same keys as a structured argument, so an MCP caller can state what a CLI user could. `clew/buildoptions.py` says every declaration section now has a matching option.
4. **Facts the target already wrote** (tier 3, target-fact). These are a Doxyfile's `ALIASES` and `PREDEFINED`, generator manifests, and language or platform entry points. They accumulate and are never removed by anything stated.
5. **Built-in defaults** (tiers 4 and 5). Ecosystem signatures such as UDM or ingot are tier 4 and also accumulate. Name-pattern heuristics are tier 5, the provisional floor.

**When they disagree**

The rule lives in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. In short, "you can correct our guesses; you cannot un-discover a fact."

- **Flag vs. declaration for the same option:** the flag wins outright. It replaces the declared value, not merges with it (`test_explicit_flag_wins_over_the_declaration`).
- **Either stated tier vs. heuristics:** a stated value displaces the tier-5 guesses. Facts from tiers 3 and 4 survive regardless. For example, passing `--entry-patterns` does not drop `main`.
- **Empty flag:** `--entry-patterns` with no values withdraws the flag and falls back to the declaration or defaults. It does not state an empty set.
- **Duplicates:** a fact restated by the operator is not duplicated.
- **Scope specifically:** the repo's own docs (`clew/tiers.py`, `tests/test_build_docs_db.py`) give the order as scope declaration, then guard config, then Doxyfile. A declaration beats a built-in default everywhere.
- **Unknown section:** `load_declaration` raises `DeclarationError` and names the allowed sections. It does not silently ignore them. Keys prefixed `x-` are tolerated with a warning, so an older clew can read a newer file. A test name says a malformed declaration "degrades to defaults," so the refusal and the degrade paths both exist, and I did not verify which applies to each case.
- **Old config:** `.doxygen-guard.yaml` is no longer read. A repo that has not moved its declaration gets the built-in defaults, with no fallback.
- **Recording:** the winning tier is stored in `build_meta`, so a reader can see which layer produced a given index.

I also tried `propose_declaration`, which would show what the defaults miss for this repo, but the tool needs permission you have not granted, so I did not run it. This repo's own `.clew.yaml` only sets the `guard:` section and points `requirements` at `requirements.yaml`, so the index builds it on defaults.