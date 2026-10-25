**Short answer:** the index file set is decided by the repo's own `index_scope:` declaration in `.clew.yaml`. If there is none, clew indexes the whole repository minus what git ignores. The Doxyfile does not decide scope anymore.

**The decision, in order** (`clew/scope.py`, `derive_scope` at line 639)

1. `_declared_index_scope` (line 991) reads `index_scope:` from `.clew.yaml`. It accepts only `roots` and `excludes`.
   - Roots are repo-relative. Absolute or `../` entries are refused (`_existing_paths`, line 1247).
   - Roots that don't exist are dropped with a warning.
   - Roots are taken at their word and never walked, so a foreign clone under a declared root is indexed.
   - A section that is present but unusable (unknown keys, no usable `roots`) is rejected. `derive_scope` logs a WARNING and falls through to the whole-repo tier with the rejection as the reason (lines 669–674).
2. If nothing usable is declared, `whole_repo_scope` (line 683) applies. The single root is the repo, and the excludes are:
   - Git-ignored paths, from `git ls-files --others --ignored --exclude-standard --directory` (line 865).
   - Each nested git tree's own ignores, since `git ls-files` cannot see through a submodule boundary (line 716).
   - Dot-directories and `__pycache__`/`node_modules`, collected by `_pruned_dirs` (line 908).
   - The doxygen-guard `files:` pattern is explicitly not used (docstring, lines 17–20).
3. Nested git trees are indexed, not excluded (gh#333). They are tagged external later by `external.py`, so they are not cut out of the file set.

**What happens with no declaration**

- `derive_scope` returns `source="whole-repo"`. `derive_scope_logged` (line 1313) logs a WARNING: "indexing the WHOLE repository — no index_scope is declared…".
- A repo that says nothing gets everything git doesn't ignore, including vendored submodules and clones.
- If the directory is not a git repo, `_gitignored_paths` logs a warning and returns nothing. Nothing is excluded except the dot/cache directories, so the scope is wider than intended.
- `_MAX_DEPTH` is 16. Deeper directories are taken wholesale and recorded (`depth_limited_paths`).

**Doxygen's own filters** (`clew/doxygen.py`, `clew/treescan.py`)

Once scope is set, doxygen still applies `FILE_PATTERNS`, which clew forces to its own default list (`DOXYGEN_DEFAULT_FILE_PATTERNS`, line 203). `RECURSIVE` is forced to YES. A repo's own `FILE_PATTERNS` is overridden, so file extension still decides what is read. Doxygen's `EXCLUDE`/`EXCLUDE_PATTERNS` are cleared when a declared scope replaces `INPUT` (`doxygen.py` lines 256–257 and 323–324).

A Doxyfile still matters for `ALIASES` and `PREDEFINED`. If the repo ships none, one is synthesized.

**A doc inconsistency**

`docs/languages/C_INTEGRATION.md` (lines 22–26) says a surviving `EXCLUDE_PATTERNS` can still drop whole trees when `INPUT` is replaced. The code clears `EXCLUDE_PATTERNS` in that case, so the doc is stale on this point.

I read the source and the index. I did not run a build to confirm the resulting file counts.