**Short answer:** the repo's own `index_scope:` declaration decides which files are indexed. If the repo declares nothing, clew indexes the whole repository, minus what git ignores and minus dot and cache directories. The Doxyfile no longer decides this.

**The decision, in order** (from `clew/scope.py`):

1. **`derive_scope(repo_root)`** is the single entry point. It resets the depth-limit record, then asks for a declaration.
2. **Declared tier.** `_declared_index_scope` reads `index_scope:` from the repo's `.clew.yaml` (or from a scope a caller passes in directly).
   - Only `roots` and `excludes` are accepted. Any other key rejects the whole declaration.
   - `roots` is required. A root that doesn't exist on disk is dropped. If no root survives, the declaration is rejected.
   - Declared roots are taken at their word and never walked. A clone nested under a declared root is indexed too, then tagged by `external.py`.
3. **Whole-repo tier.** Reached when nothing is declared, or when the declaration is rejected. `whole_repo_scope` makes the repo root the single input root and subtracts:
   - Paths git ignores (`git ls-files --others --ignored --exclude-standard --directory`). This also runs per nested git tree, since the parent's `git ls-files` can't see inside a submodule.
   - Dot and cache directories, found by `_pruned_dirs`. Descent stops at nested git trees, but their own top-level dot directories are still collected.
   - Nested git trees are *included*, not cut out. An earlier version excluded them; gh#333 reversed that.
4. **Rejection is loud.** A rejected declaration logs a warning and the whole-repo reason says why it was rejected. The `reason` text names the declaration file, so a user can see which tier applied and why.

**What happens when nothing is declared:**

- The log says no `index_scope` is declared and names the whole repository as the scope, including nested git trees.
- Git-ignored paths and dot/cache directories are excluded.
- A Doxyfile, if present, still supplies aliases and predefines, but not the input set.
- The reason text ends with advice on how to declare a narrower scope.

**Limits of this answer:** I read `derive_scope`, `whole_repo_scope`, `_declared_index_scope`, `_gitignored_paths`, `_pruned_dirs` and `nested_repo_roots` from the index. I did not read the per-file type filter that runs after scope is chosen, so I can't say exactly which extensions are kept. The `clew.query.models.IndexScope` record also carries a `not_indexed` count by extension, which reports what was in scope but produced no rows.