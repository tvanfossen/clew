Clew decides the file set in two steps: a scope is chosen first, then doxygen walks that scope with a fixed set of patterns and excludes. The index shows no per-file filter beyond these, but I did not read the doxygen invocation itself, so the last step is inferred from how the scope is passed to it.

**Step 1: choose the scope (`clew/scope.py`).** `derive_scope` (`scope.py:639`) has two tiers, and the Doxyfile is no longer one of them (gh#333).

1. **Declared.** If the repo's `.clew.yaml` has an `index_scope:` block, `_declared_index_scope` (`scope.py:991`) reads it. It accepts only `roots:` and `excludes:`, and it refuses unknown keys by name. Each root is resolved relative to the repo, and anything that resolves outside the repo or does not exist on disk is dropped with a warning (`_existing_paths`, `scope.py:1247`). The check is "resolve, then contain, then stat", because of an earlier security finding (H5). A block with no usable roots is rejected, and the rejection reason is logged. `derive_scope` then falls back to the whole-repo tier, but `declared_scope_rejection` lets the CLI and MCP refresh paths refuse instead.
2. **Whole repository.** If nothing is declared, or the declaration is unusable, `whole_repo_scope` (`scope.py:683`) makes the repo root the single INPUT root. The subtractions are:
   - everything git ignores (`git ls-files --ignored --exclude-standard --directory`, run through `git_argv` so a target's `.git/config` cannot execute code), including the ignores inside each nested git tree;
   - dot-directories and `__pycache__`/`node_modules` (`_skip_dir`, `scope.py:490`), pruned by `_pruned_dirs`;
   - nothing else. Nested git trees (submodules, vendored clones) are indexed and tagged in `external.py`, not excluded.

`derive_scope_logged` (`scope.py:1313`) makes the choice visible. A declared scope logs at INFO. The whole-repo default logs at WARNING with its reason, so an unchosen boundary is never mistaken for a chosen one.

**Step 2: what doxygen is given.** A repo's own Doxyfile still supplies ALIASES and PREDEFINED, but its INPUT is replaced by the chosen roots. If the repo ships no Doxyfile, one is synthesized over the declared scope. `effective_file_patterns` (`clew/doxygen.py:279`) returns a forced default pattern set, not the target's FILE_PATTERNS (gh#340). The target's own patterns are only reported. The doxygen-guard `files:` pattern is not a scope tier at all; it answers what must be documented, not what should be indexed.

**When nothing is declared.** The whole repository is indexed, less what git ignores and the dot/cache directories. The reason is recorded and logged at WARNING. The walk stops at depth 16 (`_MAX_DEPTH`, `scope.py:62`), and any directory it stops at is recorded in `depth_limited_paths` rather than silently treated as empty.

Two things I could not settle from the index: the exact doxygen command line that consumes these roots and excludes, and whether a language-level filter (`clew/treescan.py`) applies after doxygen. Reading `clew/doxygen.py` or the build driver would answer both.