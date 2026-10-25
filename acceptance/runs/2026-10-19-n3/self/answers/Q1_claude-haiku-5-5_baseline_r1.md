**Short answer:** nothing is "declared" by default, so clew indexes the whole repository, minus what git ignores and a few directory classes. The only thing that narrows that is an `index_scope:` section in the repo's `.clew.yaml`.

**1. Declared scope (the one tier that states a boundary)**

`derive_scope` in `clew/scope.py` (~line 639) checks for an `index_scope:` block with `roots` and `excludes`:

- **Usable declaration:** the listed roots are taken at their word and never walked. Roots that don't exist are dropped with a warning. `excludes` are applied as given.
- **Present but unusable** (bad keys, or no roots left after dropping missing ones): this is not treated as absent. It logs a WARNING with the reason and falls back to the whole-repo tier, with the rejection carried in the reason. The CLI and MCP refresh paths can refuse instead, using `declared_scope_rejection`.
- **Stated by a caller:** a tool-supplied `index_scope` (the `stated` argument) goes through the same construction. Passing a non-default `--scope` alongside a stated `index_scope` is refused with exit 1, because that scope would otherwise be silently ignored (`clew/cli.py` ~line 758).

**2. No declaration: the whole-repo tier (the default since gh#333)**

`whole_repo_scope` (~line 683) returns one root, the repo itself, and an exclude list built from:

- **Git-ignored paths**, from `git ls-files --others --ignored` on the parent. Each nested git tree (submodule or vendored clone) is checked against its own `.gitignore`, because the parent's `ls-files` stops at the submodule boundary.
- **Dot-directories and known cache/vendor names**, pruned by `_skip_dir` during the walk. The walk stops at nested git trees, and at depth 16 (`_MAX_DEPTH`). Directories cut off by the depth limit are recorded for reporting.
- **Nested git trees are indexed, not excluded.** `external.py` tags their rows afterward so they can be told apart in answers.

Things that do not decide the set in this tier:

- **The Doxyfile's INPUT list.** The old fallback was removed in gh#333. A Doxyfile still supplies ALIASES and PREDEFINED, but not the indexed files.
- **doxygen-guard config** (`guard:` in `.clew.yaml`). It answers what must be documented, which the code says is a different question from what should be indexed.

**3. After scope resolution**

Scope only decides which files are read. Binary files are removed by `_drop_binary_files` (and added to the extra-exclude list), and `--extra-input` paths are appended on top. I did not trace the full ordering of every later filter.

**4. This repo**

`.clew.yaml` declares only `guard:` (output dir, `impact.requirements`, validate excludes and tag pattern). It has no `index_scope:`, so a build of this repo uses the whole-repo tier. Under that tier, `acceptance/`, `tests/` and `scripts/` are indexed, because those excludes only apply to the gate.

One note: a PostToolUse hook suggested a `dossier` call for `scope.py`. I don't have that tool in this session, and reading the source was enough for this answer.