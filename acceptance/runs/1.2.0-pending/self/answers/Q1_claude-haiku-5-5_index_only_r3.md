Short answer: a repo's own `index_scope:` declaration is the only thing that decides the scope. If nothing is declared, clew indexes the whole repository minus what git ignores and minus dot and cache directories. The Doxyfile does not decide it.

**The decision, in order** (`derive_scope` in `clew/scope.py:639`)

1. **Declared scope.** `_declared_index_scope` reads `index_scope:` from `.clew.yaml` (or a scope stated by a tool caller). Its `roots:` list is required and `excludes:` is optional. Declared roots are taken at their word and never walked. Roots that don't exist on disk are dropped.
2. **Rejected declaration.** If a declaration is present but unusable, it is not treated as absent. Examples are a non-mapping section, an unknown key such as `exclude:` for `excludes:`, or no surviving root. The reason is logged as a WARNING and the whole-repo tier is used with that reason attached.
3. **Whole repository.** If no `index_scope:` section exists, `whole_repo_scope` is used. This is the default since gh#333.

**What "whole repository" means when nothing is declared** (`whole_repo_scope`, `clew/scope.py:683`)

- The single root is the repo root. Nested git trees (submodules, vendored clones) are included, not cut out. They are tagged afterwards by `external.py` so answers can tell the codebases apart.
- Excludes are:
  - everything `git ls-files --ignored --exclude-standard --directory` reports for the parent and for each nested tree. `.gitignore` is the main source. Git runs through `git_argv`/`git_env`, so a target's own `.git/config` cannot execute commands.
  - dot and cache directories found by `_pruned_dirs`. The walk stops at nested trees and keeps only their top-level dot directories. It stops at depth 16 and records where it stopped.
  - `__pycache__` and `node_modules` (`_SKIP_DIR_NAMES`).
- The Doxyfile's `INPUT` is ignored for scope. A Doxyfile still supplies `ALIASES` and `PREDEFINED`. The `doxygen-guard` `files:` pattern is not read at all. The code's reasoning is that a documentation target is not a reasoning boundary. On mbedtls, honouring `INPUT = ../include` indexed 1,571 headers and none of the 108 `library/*.c` implementations.
- If git is missing or the tree is not a repository, nothing is excluded. The scope is wider than asked, and a WARNING says so.

**Logging.** The chosen tier and its reason are logged on every derivation. The reason names the file that was read, or says that no `index_scope` was declared and that the whole repo is the scope.

**What I could not verify.** The index gave me the scope resolver and its helpers, but not the body of `_skip_dir`, so I cannot list every directory name it skips beyond `__pycache__`, `node_modules` and dot directories. I also did not read the `.clew.yaml` loader itself, so I cannot confirm where that file is searched for beyond what `_declared_index_scope` shows.