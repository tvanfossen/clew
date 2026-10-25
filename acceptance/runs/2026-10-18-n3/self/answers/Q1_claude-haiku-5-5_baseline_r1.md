**Short answer:** the repository's own `index_scope:` declaration decides the roots. If there isn't one, the whole repository is the scope, minus what git ignores and a few directory names. Nothing filters by file extension at the walk stage. Extensions only matter later, in the doxygen and per-language parsers.

**1. Declared scope (tier 1).** `derive_scope` in `clew/scope.py:639` first calls `_declared_index_scope`, which reads `index_scope:` from `.clew.yaml`. A declared `roots:` list replaces the scope entirely; `excludes:` is subtracted from it. A root that doesn't exist on disk is dropped. If the section is present but unusable (wrong type, unknown key such as `exclude:` for `excludes:`, or no surviving root), it is rejected with a logged warning and the build falls back to whole-repo. The rejection reason is carried through to the log so the warning doesn't contradict itself.

**2. Whole-repo default (tier 2).** When nothing is declared, `whole_repo_scope` (`clew/scope.py:683`) makes one root: the repo itself. Then it subtracts:
- **Git-ignored paths.** `git ls-files --others --ignored --exclude-standard --directory` (`_gitignored_paths`, `clew/scope.py:845`). This runs through `git_argv`/`git_env` so a cloned repo's config can't execute code.
- **Dot and cache directories.** Anything starting with `.`, plus `__pycache__` and `node_modules` (`_skip_dir`, `clew/scope.py:490`). These are pruned by `_pruned_dirs`.
- **Nested git trees are indexed, not excluded.** Their own `.gitignore`s are applied separately, because the parent's `git ls-files` can't see inside a submodule. Nested trees are tagged later by `external.py`.
- **Walk depth.** Descent stops at 16 levels; anything deeper is recorded and logged.

The `.clew.yaml` in this repo declares only `guard:` and no `index_scope:`, so this repo indexes on the whole-repo tier. Its header comment says the same.

**3. Doxyfile and gate are not inputs.** A repo's Doxyfile `INPUT` no longer decides scope (gh#333). The Doxyfile still supplies ALIASES and PREDEFINED. The doxygen-guard `files:` pattern is also not a scope tier; it answers what must be documented, not what gets indexed.

**4. Walk and binary filter.** `enumerate_tree` (`clew/treescan.py:203`) walks the roots with the excludes pruned during the walk. It is deliberately not extension-filtered. Then `_drop_binary_files` (`clew/cli.py:2554`) removes files that `lang_parsing_substrate.classify_file` marks as binary (magic numbers and NUL/control-byte ratios). Those files are added to the exclude channel before doxygen runs. Size is not limited, so a large generated `.c` still counts as source.

**5. Extension filtering happens later.** Doxygen is forced to its own default `FILE_PATTERNS` list (`clew/doxygen.py:203`). A repo's declared `FILE_PATTERNS` no longer vetoes files that scope admitted (gh#340). That list covers C/C++, Java, C#, PHP, Fortran, Python, Markdown, VHDL and others. Languages outside it, such as Rust and JS/TS, are picked up by their own front ends: for example, `filedocs.py` picks files by each extractor's `EXTENSIONS`. I did not trace the JS/TS and Rust paths end to end, so treat the exact handoff for those as unverified.

**What happens with nothing declared, in order:**
1. Root = repo, no declaration rejection.
2. Git-ignored paths, dot/cache directories, and nested-tree gitignores are excluded.
3. Everything else is walked, including nested git trees.
4. Binary files are dropped and logged at INFO.
5. Doxygen parses what matches its default patterns; language front ends parse their own extensions.

The log line for this case says "no `index_scope` is declared … so the whole repository is the index scope", which is the easiest way to confirm it on a real build.