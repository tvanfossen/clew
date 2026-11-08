The ways to tell clew how to index a repository, from strongest to weakest:

| Route | Where it lives | Tier | Scope |
|---|---|---|---|
| CLI flag (e.g. `--exclude`, `--entry-patterns`, `--extra-input`) | argv of one build | 1 (explicit) | one build, though `--exclude` is recorded into the index and replayed by later builds |
| `--declare FILE` | a YAML document stated for this build | 1 (explicit) | one build, recorded in the index |
| `options=` argument to `build_index()` or MCP `index(action="refresh")` | same mapping as `--declare`, passed by an embedding caller | 1 (explicit) | one build |
| `<repo>/.clew.yaml` | the target's own standing declaration | 2 (declared) | every build of that repo |
| Target-owned files (a Doxyfile's PREDEFINED/ALIASES, a generator manifest, `toolchain.toml`, `suppress.toml`) | the repo's own tooling | 3 (target-fact) | read as facts |
| Built-in defaults (ecosystem signatures, name heuristics) | clew | 4 and 5 | the floor |

The sections a declaration can carry include `index_scope`, `preprocessor`, `requirements`, `thread_patterns`, `shared_key_patterns`, `locks`, `dispatch`, `kconfig`, `entry_patterns`, `enrich` and `sub_indexes`. Only `preprocessor`, `kconfig`, `index_scope` and `sub_indexes` can be stated inline through `--declare` or `options=`. The `guard:` section of the same file belongs to the quality gate, and the index drops it.

Environment variables are not index configuration. `CLEW_JOBS` sets the shared-parse worker count, `CLEW_HOOK_DISABLE` turns off the hook, and `CLEW_STATE_HOME` moves state. None of them changes what gets indexed.

**When two of them disagree**, the rule is in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. In plain terms, you can correct clew's guesses, but you cannot un-discover a fact.

- **Flag vs. declaration (same option):** the flag wins outright and replaces the declared layer. The declared value is not merged in. This is `_stated_layer` in `tiers.py` and `_declared_or_flag` in `cli.py`.
- **`--declare` vs. `.clew.yaml` (same section):** the stated section replaces the declared section as a whole. It is not a deep merge. `_with_stated_sections` (`cli.py`) gives the reason: a merged `preprocessor` would describe a configuration neither side stated. Stating `{}` withdraws the statement, and the declaration answers again.
- **Flag or declaration vs. target facts or heuristics:** target facts (tier 3) and ecosystem signatures (tier 4) accumulate, and no stated tier removes them. Heuristics (tier 5) are the only layer a stated value displaces. So passing `--entry-patterns` no longer silently drops `main`.
- **Flag vs. flag (e.g. `--extra-input`):** these append rather than replace.
- **Empty values:** an empty flag or an empty `--declare` document is treated as "state nothing", and the next tier down answers.

Each build records which tier won for each option in `build_meta`, so a reader can tell what was actually used.

I read the README, `cli.py`, `tiers.py`, `declaration.py`, `buildoptions.py` and `scope.py` directly. I did not run a build, so the precedence above is from the code and its docstrings, not from observed behaviour. I also did not trace how `toolchain.toml` and `suppress.toml` exclusions combine with `index_scope`.