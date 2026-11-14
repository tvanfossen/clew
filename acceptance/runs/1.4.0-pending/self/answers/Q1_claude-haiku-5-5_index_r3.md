**Short answer:** the index scope is decided by `derive_scope` in `clew/scope.py`. A declared `index_scope:` in `.clew.yaml` wins. If nothing usable is declared, the whole repository is the scope, minus what git ignores and the dot and cache directories. A Doxyfile never decides the file set.

**The decision, in order**

1. `derive_scope(repo_root, stated)` (`clew/scope.py:639`) is the single entry point. It clears the depth-limit record, then asks `_declared_index_scope` for a declaration.
2. `_declared_index_scope` (`clew/scope.py:991`) reads `index_scope:` from `.clew.yaml`. A caller can also pass a scope directly, which is the same construction with a different reason string.
   - No `index_scope:` section returns `None`, and the code falls through to the whole-repo tier.
   - A section that is present but unusable is rejected with a reason. Examples: it is not a mapping, it has an unknown key such as `exclude:` for `excludes:`, or it has no `roots:` that exist on disk. The rejection is logged as a warning, and the build falls back to the whole repo with the rejection named as the reason. It does not silently widen.
   - A declared `roots:` list is taken at its word and never walked. `excludes:` only subtracts from it, and `excludes` alone does nothing.
3. If nothing usable is declared, `whole_repo_scope` (`clew/scope.py:683`) returns one root, the repository itself. Its `excludes` are:
   - the paths git ignores, from `git ls-files --others --ignored --exclude-standard --directory` (`_gitignored_paths`, `clew/scope.py:845`), run through `git_argv` and `git_env` so a target's own `.git/config` cannot run code;
   - the same ignore list for each nested git tree, since the parent's `ls-files` cannot see inside a submodule;
   - dot-directories plus `__pycache__` and `node_modules` (`_skip_dir`, `_SKIP_DIR_NAMES`).

**What the defaults do not consult**

- **Doxyfile `INPUT`.** A Doxyfile still supplies ALIASES and PREDEFINED, but its INPUT is replaced. Honouring it would index only headers for a repo like mbedtls.
- **The doxygen-guard `files:` pattern.** That pattern answers what must be documented, not what should be indexed. A test asserts a gate pattern alone derives no index roots.
- **Nested git trees.** These are indexed, not excluded. `external.py` tags their rows so two codebases in one index can still be told apart.

**What this repo shows now**

`index(action=status)` reports the decision for this repo: `.clew.yaml` exists but carries no `index_scope`, so `source: whole-repo`, roots `.`, excludes `.git, .claude-plugin, .github`. That gives 435 files in scope and 397 indexed. The other 14 are listed by extension or reason, for example `.csv=3`, `.rs=2`, `.toml=2`. I did not trace each of those 14 to its reason. Binary files are dropped separately (REQ-DDB-PIPE-011, stamped via `_skipped_files_scope` in `clew/cli.py:2594`), and the walk stops descending at a fixed depth, with the stops recorded.

**Caveat:** I used the index for the scope logic and read the status payload. I did not open `_drop_binary_files` or the extension-level filter to confirm their exact rules.