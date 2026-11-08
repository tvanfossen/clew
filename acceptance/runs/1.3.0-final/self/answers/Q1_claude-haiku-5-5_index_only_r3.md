Under the no-declaration case the answer is simple: the whole repository is the index root, minus what git ignores and minus dot and cache directories. The decision is made in `clew/scope.py`, through `derive_scope`.

**How the decision is made**

1. `derive_scope(repo_root)` (`clew/scope.py:639`) is the single entry point. It clears the depth-limit record first, then asks `_declared_index_scope` for a declaration.
2. `_declared_index_scope` (`clew/scope.py:991`) reads an `index_scope:` section from the repo's `.clew.yaml`. The only keys it accepts are `roots` and `excludes` (`_INDEX_SCOPE_KEYS`, line 406). Any other key refuses by name. A `roots:` list is required, and each root must exist on disk; missing roots are dropped with a warning. A malformed section returns a `_Rejected` reason instead of quietly falling through.
3. If the declaration is usable, its roots and excludes become the scope. If it is present but rejected, `derive_scope` logs a WARNING and falls through to the whole-repo tier, with the rejection reason carried into that tier's reason string. The CLI and MCP refresh paths call `declared_scope_rejection` first and refuse the build instead, so a rejected declaration does not silently widen the index in those paths.
4. If nothing is declared, `whole_repo_scope(root)` (`clew/scope.py:683`) takes over.

**What the whole-repo tier does**

- Its single root is the repository itself, and nested git trees are included.
- Excludes come from `git ls-files --others --ignored --exclude-standard --directory`, run through `git_argv` and `git_env` so a target's own `.git/config` cannot execute code (`_gitignored_paths`, line 845). The same ignore sweep is repeated inside each nested git tree, because the parent's git cannot see a submodule's `.gitignore`.
- Dot-directories and `__pycache__` / `node_modules` are added as explicit EXCLUDE entries (`_pruned_dirs`, line 908; `_skip_dir`, line 490). The reason is that the whole-repo root is handed to doxygen unwalked, so a rule that only pruned a walk would never apply.
- The walk stops at nested git trees, taking only their top-level dot-directories, and stops at a depth of 16 (`_MAX_DEPTH`). Anything deeper is recorded in `_DEPTH_LIMITED`.
- The Doxyfile's `INPUT` is not consulted. Since gh#333 it is a documentation target, not a reasoning boundary. The Doxyfile still supplies ALIASES and PREDEFINED. The doxygen-guard `files:` pattern is not read either, because it answers what must be documented, not what should be indexed.

The tests agree with this. `test_no_declaration_yields_the_whole_repo` (`tests/test_scope.py:130`) checks that an undeclared repo gets `SOURCE_WHOLE_REPO`, roots `(repo,)`, and a reason that names `index_scope` and `.clew.yaml`. `test_dot_directories_are_excluded_from_the_whole_repo_scope` (line 157) checks that `.venv` is excluded and `src` is not.

**Two things I could not settle from the index**

- The docstring on `_declared_index_scope` still says a missing declaration "drops the resolution to the Doxyfile's own INPUT". That contradicts `derive_scope` and `whole_repo_scope`, which say the Doxyfile tier is gone. The code path matches the newer description, so the docstring looks stale.
- I did not confirm whether doxygen `FILE_PATTERNS` (the file-type filter) applies under the whole-repo tier, or how `treescan.py`'s `_matches_file_patterns` and `roots_matching_no_file_pattern` fit in. So the answer above covers which trees and paths are in or out, not the full per-extension filter.