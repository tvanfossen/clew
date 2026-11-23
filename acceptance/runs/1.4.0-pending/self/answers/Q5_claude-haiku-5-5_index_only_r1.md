Clew has three ways to tell it how to index a repository, and a fixed rule for when they conflict. I answered from the index alone, so the details below come from docstrings and tests, not from reading the source.

**The ways to say so**

1. **Built-in defaults.** Clew assumes nothing repo-specific. These are the baseline when nothing else is stated.
2. **Declaration file: `<repo>/.clew.yaml`.** This is the repo's standing statement, found from the repo root. It is the route that works through the MCP server, which passes no CLI flags. Each top-level section mirrors a standalone manifest format, so a repo can move an existing file's contents in unchanged. Sections include `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `dispatch`, `preprocessor`, `kconfig`, `requirements`, `locks`, `doxyfile`, `sub_indexes`, and others. The `guard:` section is the gate's config and lives in the same file. The index ignores it.
3. **Explicit statements at call time.** These are CLI flags such as `--shared-key-patterns` or `--doxyfile`, or, for an embedding caller, one structured `options` argument to `build_index`/`build_or_refresh`. The option names are the same as the declaration section names, with one documented alias, `predefined`. `options` can also carry an inline document instead of a path.

Some things are deliberately not declarations. `--scope`, `--index-cache` and `--rebuild` describe one run, not the repository, so they have no section.

**When they disagree**

- **Explicit beats declared.** A flag or `options` value overrides the `.clew.yaml` section for that build. The file is the standing statement and the flag is a deliberate one-off. An empty stated value (`{}`) withdraws the statement and falls back to the declaration.
- **Validation is all-or-nothing.** `apply_options` checks every entry before assigning any of them, so one bad entry leaves the settings untouched. It does not half-apply the policy.
- **Unknown section names are refused.** A misspelled top-level key fails and names the probable cause. Keys with an `x-` prefix are tolerated and ignored. A malformed declaration degrades to defaults.

**The general rule (five tiers)**

The formal precedence lives in `clew/tiers.py`:

| Tier | Source | Combines by |
|---|---|---|
| 1 | CLI flag / `options` | replaces the layer below |
| 2 | `.clew.yaml` | replaces |
| 3 | Facts someone already wrote, such as a Doxyfile's aliases or predefined macros | accumulates |
| 4 | Known-ecosystem signatures | accumulates |
| 5 | Name-pattern heuristics, the floor | replaces |

The resolved set is `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. A stated value displaces the guesses, but it cannot remove facts the repo has already recorded. The module's summary is "you can correct our guesses; you cannot un-discover a fact."

The point of this is that an explicit value can't silently drop something. Earlier, passing `--entry-patterns` dropped `main` and nothing reported it. Under this rule, `main` survives whatever a user states.