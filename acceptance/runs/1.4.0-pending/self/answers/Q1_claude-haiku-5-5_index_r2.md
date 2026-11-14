**Short answer:** with nothing declared, clew indexes the whole repository. Every file under the root is a candidate, minus what git ignores, minus dot and cache directories, and the extension filter then applies. Declaring an `index_scope:` is the only thing that narrows the walk to chosen roots.

**Decision order** (`derive_scope`, `clew/scope.py:639`):

```
stated by a tool call (tier 1)  ──► _declared_index_scope(root, stated)
        │ none
        ▼
index_scope: in .clew.yaml      ──► _declared_index_scope(root)
        │ absent / unusable
        ▼
whole_repo_scope(root)          ──► roots=(repo root,), excludes=derived
```

1. **Declared scope.** `_declared_index_scope` (`clew/scope.py:991`) reads `index_scope:` from `.clew.yaml`. `roots` is required and each root must exist on disk; a missing root is dropped with a warning. `excludes` is optional and only trims. Unknown keys inside the block are refused by name, as is a non-mapping section or a block with no usable roots. These are rejected, not silently treated as absent.
2. **Whole repo, when nothing usable is declared.** `whole_repo_scope` (`clew/scope.py:683`) is the default tier, not a last resort. Its single root is the repository, and its excludes are:
   - **Git-ignored paths**, from `git ls-files --others --ignored --exclude-standard --directory`, run with `git_env()` so a target's own `.git/config` cannot execute code. This runs per nested git tree too.
   - **Dot and cache directories**, via `_pruned_dirs` and `_skip_dir` (names starting with `.`, or in `_SKIP_DIR_NAMES`).
   - The walk stops at nested git trees, keeping only their top-level dot directories, and stops at a depth limit (`_MAX_DEPTH`, recorded in `_DEPTH_LIMITED`).
   - Nested trees are indexed, not excluded. `external.py` tags their rows afterwards so answers can still tell codebases apart.
   - The Doxyfile no longer supplies INPUT (gh#333). It still contributes ALIASES and PREDEFINED.
3. **Extension filter.** A file must match doxygen's `FILE_PATTERNS` and not match `EXCLUDE_PATTERNS` (`in_doxygen_scope`, `clew/doxygen.py:308`). `effective_file_patterns` (`clew/doxygen.py:279`) returns the forced `DOXYGEN_DEFAULT_FILE_PATTERNS` whatever the target's Doxyfile declares (gh#340). So the target's own patterns do not decide which extensions are indexed. I did not read the constant's value, so I can't list the extensions.

**Live check on this repo** (`index(action='status')`):
- `.clew.yaml` exists but carries no `index_scope`, so `source: whole-repo` and root `.`.
- 435 files in scope, 397 indexed, 14 not indexed. The not-indexed set is listed by extension: no-extension=3, .csv=3, .rs=2, .toml=2, .jsonl=1, .lock=1, .motor=1, .sql=1.
- Excludes are `.git`, `.claude-plugin`, `.github`. I did not trace why the two `.rs` files fall outside the extension filter.

**What "nothing declared" means in practice:** the index covers the whole tree, including vendored trees. The build reports the reason in its log, and `propose_declaration` only proposes YAML; it never applies it. Narrowing requires writing an `index_scope:` with `roots:`.