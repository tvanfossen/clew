**Short answer:** the index is every file under the repository root, minus what git ignores, minus dot and cache directories, minus binaries, and minus anything the owner excludes. A `.clew.yaml` `index_scope:` block can replace that default with explicit roots. Nothing is filtered by file extension at this stage. I read the scope and walk code and did not run a build, so the claims below come from source, not from observed output.

**Decision flow**

```
clew index <repo>
  │
  ├─ load <repo>/.clew.yaml  →  index_scope: section?
  │     ├─ yes, usable  → roots = declared dirs that exist; excludes = declared list
  │     ├─ yes, broken  → logged WARNING, falls through to whole-repo
  │     └─ no section   → whole-repo tier (the default)        [clew/scope.py derive_scope]
  │
  ├─ enumerate_tree(roots, excludes)   walk; NO extension filter   [clew/treescan.py]
  ├─ toolchain.toml index_globs        → extra excludes (only if declared)  [cli._apply_toolchain_exclusions]
  ├─ --exclude PATH… (operator)        → extra excludes, recorded into the index
  ├─ binary files                      → dropped and reported as skipped   [cli._drop_binary_files]
  └─ per-language front ends           → parse what they understand
```

**The declared path.** `_declared_index_scope` reads `index_scope:` with `roots` and `excludes` as the only accepted keys. Any other key rejects the whole block. Roots are repo-relative. A root that does not exist is dropped with a warning. If no root survives, the block is rejected as "declares index_scope but no usable roots", and the build falls back to whole-repo. `excludes` alone does nothing, because `roots` replaces the scope and is required.

**The undeclared path (the zero-config default).** `whole_repo_scope` produces one root: the repository itself. Its excludes are:

- **Git-ignored paths.** Collected with `git ls-files --others --ignored --exclude-standard --directory`. It runs through `git_argv` and `git_env`, so a cloned repo's own `.git/config` cannot execute code.
- **Nested git trees.** Their own ignored paths are collected per tree, because `git ls-files` stops at submodule boundaries.
- **Dot-directories and `__pycache__`/`node_modules`.** Pruned by a walk. The walk stops at nested trees (taking only their top-level dot-directories) and at depth 16.

Nested repositories are indexed and tagged, not excluded (gh#333). The repo's Doxyfile no longer supplies the INPUT. It still contributes aliases and predefined macros.

Two consequences follow from the code:

- A `.gitignore` entry only removes untracked files. `--others` lists untracked ignored paths, so a tracked file that matches an ignore pattern stays in scope.
- The default is wide. `vendored/`, third-party trees and `docs/` all get indexed unless gitignored. `docs/CORE_HYPOTHESIS.md` says this is intentional.

The build logs the choice. A declared scope logs at INFO. The whole-repo default logs at WARNING with the reason, for example "no index_scope is declared … so the whole repository is the index scope."

**What is not a filter.** `enumerate_tree` is deliberately not extension-filtered. Its docstring argues that hashing every file keeps invalidation conservative. Extension logic appears later, in the language front ends and in `filedocs.EXTENSIONS`. I did not trace every front end, so I cannot list the exact extensions that produce symbols.

**Stale comment to fix.** The docstring of `_declared_index_scope` still says a missing declaration "drops the resolution to the Doxyfile's own INPUT". That fallback was removed in gh#333, so the comment contradicts the code.

**This repo.** Its own `.clew.yaml` declares only `guard:` and no `index_scope:`. Its index therefore takes the whole-repo default. `tests/` and `acceptance/` are excluded only from the gate's validation, not from the index.