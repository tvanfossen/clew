Clew takes its index configuration from four places, plus a fallback. When two of them name the same option, the more explicit one replaces the less explicit one as a whole. Exclusions are the exception: they combine.

**The ways to say so**

| Source | Tier | What it does |
|---|---|---|
| Built-in defaults | 5 (heuristic) | Name-pattern guesses, such as `main` for entry points. A stated value displaces them. |
| The repo's `.clew.yaml` | 2 (declared) | Standing declaration, read from the repo root. Holds `index_scope:` (`roots`, `excludes`) plus per-option sections like `entry_patterns`, `preprocessor`, `thread_patterns`. |
| `--declare FILE`, or the `options` argument of `build_index()` / MCP `index(action="refresh")` | 1 (explicit) | Stated for one build. Same vocabulary as `.clew.yaml`, so it works for repos you cannot edit. |
| `--exclude PATH` | 1 | Operator exclusions. Recorded in the index and replayed by later builds unless overridden. |
| `toolchain.toml` `[ignore].paths` and `suppress.toml` entries with `tool = "*"` | Shared file | Expanded to concrete paths and added to the build's excludes. Entries with `tool = "clew"` affect only the doc gate, not the index. |
| The Doxyfile (discovered, or `doxyfile` option) | Target fact | Its ALIASES, PREDEFINED and similar are used. Its INPUT is replaced by the derived scope (gh#333). |

With nothing declared, the scope is the whole repository, minus what git ignores. Nested git trees are included and tagged, not cut out.

**When two disagree**

- **Same option at tier 1 and tier 2.** Tier 1 wins. The replacement is per section, not a deep merge. The three states are: absent inherits the recorded value, empty withdraws to the declaration, non-empty replaces. The same rule applies to sub-index excludes.
- **Tier 3 and 4 facts.** These accumulate and no stated tier removes them. A Doxyfile's aliases survive a `.clew.yaml` that says otherwise.
- **`index_scope` declared plus a non-default `--scope`.** Refused with exit 1. Building would silently use a different boundary than the one stated.
- **`index_scope` declared but unusable.** Unknown keys, no existing roots, or a non-mapping makes the declaration rejected. The build logs a WARNING and falls back to whole-repo scope, with the reason naming the rejection. The build still succeeds, so check the log.
- **Declared roots that don't exist.** They are dropped with a warning. `excludes` alone does nothing, because `roots` is required.
- **Unknown keys in an inline `options` manifest.** Refused. Silently ignoring them would report a statement as honoured when it was not.
- **Toolchain excludes vs `--exclude`.** Both apply. Toolchain globs are appended to `extra_exclude`.
- **A stated `doxyfile` path that does not exist.** Refused. Falling back would build a whole-repo index while reporting success.

I read the source for this rather than running a build. I did not verify how `--exclude` interacts with an `index_scope:` `excludes` list.

Two tool results also suggested using a clew index/dossier tool to look up symbols. I did not use it; the answer above comes from reading `clew/scope.py`, `clew/tiers.py`, `clew/cli.py`, `clew/buildoptions.py`, `clew/toolchain.py` and the README.