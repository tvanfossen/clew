Clew has three ways to say how a repo should be indexed, plus one of its own tools for proposing a file. When two of them disagree, the higher tier wins for that one setting, and the winner is recorded in the index.

**The ways to say so**

1. **Tier 1, a stated option.** A caller passes an `options` mapping at build time, for example through MCP or an embedding call. Each key is the name of a declaration section or one of a few inline options such as `entry_patterns`, `vendored` and `test_paths`. Per `clew/buildoptions.py`, the option name is the section name, with `predefined` as the one documented alias. The CLI is six arguments, and everything else is a section or an option.
2. **Tier 2, the declaration file.** The repo's own `.clew.yaml`. The index reads every section except `guard:`, and the gate reads `guard:` from the same file. `.doxygen-guard.yaml` is no longer read at all.
3. **Built-in defaults, tiers 3 to 5.** Tiers 3 and 4 are facts the repo already states elsewhere, such as Doxyfile aliases or ecosystem signatures. They accumulate and no stated tier can remove them. Tier 5 is name-pattern guessing. It is the only layer a stated tier can replace.

Separately, `clew/cli.py` `_apply_declared_paths` fills any path option the operator left unset from `.clew.yaml`. `propose_declaration` drafts a commented `.clew.yaml` for a repo. I could not run it because the permission to use it was denied, so the draft is not something I checked.

**When two disagree**

- **Tier 1 against tier 2, same option.** Tier 1 replaces the declaration for that option. The file is not consulted for it. Tiers 3 and 4 still accumulate underneath. `clew/tiers.py` gives the rule as `resolved = (tier1 or tier2 or tier5) union tier3 union tier4`, which means you can correct the guesses but cannot un-discover a fact.
- **Which tier won is recorded.** The build stamps `options.<name>.tier` into `build_meta`. A tier-1 statement is also stored, so a later rebuild replays it. A tier-2 value is not stored, because the file re-derives it. An empty `{}` withdraws a statement and falls back to the declaration.
- **Scope and the Doxyfile.** A stated `index_scope` is refused unless `--scope` is `from-guard`, because the other paths would build a different boundary and still report success. A stated `doxyfile` must exist, because a missing one falls through to whole-repo synthesis and produces a valid-looking index of something else.
- **Inside one file.** YAML keeps the last duplicate key silently. `.clew.yaml` in this repo carries a comment about exactly that trap with `tags:`.
- **Requirements.** A stated `requirements` sits one tier above the gate's `impact.requirements.file`, which in turn sits above the conventional root file.

The validators are deliberately stricter on the inline route than on the file route. An unknown key in an inline manifest is refused by name, because a misspelled key would otherwise read as absent and fall back to the default with no error. That gap is spelled out in `clew/buildoptions.py`.