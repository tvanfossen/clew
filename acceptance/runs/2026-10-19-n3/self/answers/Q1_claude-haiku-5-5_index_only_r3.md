**Short answer:** the repository's own `index_scope:` declaration decides which files are indexed. If none is declared, clew indexes the whole repository, minus what git ignores and minus dot and cache directories. Doxygen's Doxyfile no longer decides this.

**How the decision is made**

1. **Resolve the scope.** `derive_scope` in `clew/scope.py:639` is the single entry point. It reads the declared `index_scope:`, and if that yields a usable root it returns the declared scope. Otherwise it falls through to `whole_repo_scope`.
2. **Declared tier.** A declaration is the only tier that is a decision about the index. A declaration present but yielding no usable root is rejected, and the rejection reason is logged. It does not silently fall back to the default.
3. **Whole-repo default.** `whole_repo_scope` (`clew/scope.py:683`) makes the repository root the single INPUT root. It then subtracts two things:
   - **Git-ignored paths.** `_gitignored_paths` (`clew/scope.py:845`) runs `git ls-files --others --ignored --exclude-standard --directory`. It runs with a sanitized git environment, and with `-c` overrides so that a cloned repo's own `core.fsmonitor` cannot execute code. If git is missing or the tree is not a repository, nothing is excluded, a warning is logged, and the scope becomes wider than the repo asked for.
   - **Dot and cache directories.** `_pruned_dirs` (`clew/scope.py:908`) collects directories matching `_skip_dir` (`clew/scope.py:490`): names starting with `.`, or in `_SKIP_DIR_NAMES`. The whole-repo root is handed to doxygen unwalked, so these rules travel as EXCLUDE entries.
4. **Nested git trees.** These are included, not cut out. Their ignore lists are read per tree, and the walk stops at a nested tree's boundary after collecting its top-level dot directories. Nested trees are tagged as external later, in `clew/external.py`, so their rows can be told apart in answers.

**What happens when nothing is declared**

- The whole repository becomes the scope, with the reason recorded as "no `index_scope` is declared for this repo", so the build log says why.
- The Doxyfile's `INPUT` is no longer used as a fallback. A Doxyfile still supplies `ALIASES` and `PREDEFINED`.
- Ignored files, dot directories and cache directories are excluded. Everything else is indexed, including vendored or nested code that the repo's `.gitignore` does not exclude.
- Files whose extension no grammar handles are never indexed. `search` reports this as a count rather than a per-file list, and `clew/propose/notindexed.py` reports what was not read.

**What I could not confirm from the index:** how `_declared_index_scope` reads `.clew.yaml` and the `--declare` option, and which exact extensions the grammars cover. The index holds no dossier for files, and I did not query those two symbols directly. Both are documented in the README and `docs/languages/C_INTEGRATION.md`, which the index surfaced as prose.