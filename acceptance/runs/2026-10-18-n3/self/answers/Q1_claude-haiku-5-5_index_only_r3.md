**Short answer:** the repo's own `.clew.yaml` `index_scope:` section decides what is indexed. If it's absent or unusable, clew indexes the whole repository, minus what git ignores and minus dot and cache directories. The Doxyfile no longer decides scope.

**The decision, in order** (`derive_scope` at `clew/scope.py:639`):

1. **A declared scope wins.** `_declared_index_scope` (`clew/scope.py:991`) reads `index_scope:` from `.clew.yaml`. `roots` is required and is repo-relative; `excludes` is optional. Roots are taken at their word and not walked, so a foreign clone under a declared root is indexed too. Nested git trees are then tagged by `external.py` rather than cut out.
2. **A declaration that is present but unusable is rejected, not silently ignored.** Examples: a non-mapping section, an unknown key (such as `exclude:` for `excludes:`), or no `roots:` that exist on disk. The rejection is logged as a warning and carries the reason into the fallback.
3. **Nothing declared falls through to `whole_repo_scope`** (`clew/scope.py:683`). Its single root is the repo itself. Its excludes come from three sources:
   - `_gitignored_paths` (`:845`) runs `git ls-files --others --ignored --exclude-standard --directory`. Nested trees get the same check against their own `.gitignore`.
   - `_pruned_dirs` (`:908`) adds dot-directories and known cache or vendor names via `_skip_dir` (`:490`). The walk stops at nested git trees, but keeps their top-level dot-directories.
   - Nested git trees are found by `nested_repo_roots` (`:785`). A directory counts as a separate repo only if it holds its own `.git`. Name-based rules such as `vendor/` do not apply.
4. **Files are then gathered** by `_files_under` (`clew/treescan.py:163`), which prunes excluded subtrees during the walk instead of filtering afterwards. Symlinked directories are not followed.
5. **Non-text files are dropped** before parsing or hashing, per the file-level doc of `clew/filetypes.py`. I could not resolve that file as a symbol, so I have not verified the exact rule.

**What happens with nothing declared:** the scope is `source=whole_repo`, and the reason string records that no `index_scope:` was declared, where clew looked, and the advice to declare one. Zero configuration therefore indexes everything git tracks, plus untracked-but-not-ignored files, minus the excludes above. The log says so, so the wider scope is visible rather than silent.

**Caveats:** the index answers from its own records, so I could not read the Doxygen-side handling or the build pipeline's full wiring. The C integration doc (`docs/languages/C_INTEGRATION.md`) says `INPUT`, `EXCLUDE`/`EXCLUDE_PATTERNS` and `FILE_PATTERNS` each independently decide scope for the C side, which is a separate path from the Python whole-repo tier above. I did not verify how the two interact in a C repo.