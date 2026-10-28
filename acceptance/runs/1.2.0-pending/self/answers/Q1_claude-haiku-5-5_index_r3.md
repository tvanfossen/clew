**Short answer:** the index's file set is decided by one resolver, `derive_scope` in `clew/scope.py`. It returns a root list plus an exclude list. A repo can declare `index_scope` in `.clew.yaml` to set those itself. If it doesn't, the default is the whole repository minus what git ignores and minus dot and cache directories. The Doxyfile does not decide scope anymore.

## The decision

```
derive_scope(repo_root, stated?)
 ├─ _declared_index_scope()             tier 1 (stated via MCP options) or tier 2 (.clew.yaml)
 │   ├─ no index_scope section     -> None
 │   ├─ bad shape / unknown key / no usable roots -> _Rejected (logged)
 │   └─ usable                     -> DerivedScope(source=declared, roots, excludes)
 └─ otherwise  whole_repo_scope()       source=whole_repo
```

**Declared scope** (`clew/scope.py` `_declared_index_scope`, around line 991):
- `roots:` is required and REPLACES the scope. `excludes:` is optional and alone does nothing.
- Roots are repo-relative. A root that doesn't exist on disk is dropped with a warning.
- Unknown keys under `index_scope:` are rejected by name. An accepted-but-unread key was called out as the project's most repeated defect.
- A declared root is taken at its word and never walked. Nested clones under it are indexed without any check.

**Whole-repo default** (`whole_repo_scope`, around line 683):
- The single root is the repository. Nested git trees are included, not excluded (gh#333). `external.py` tags their rows afterward so you can still tell codebases apart.
- Excluded: whatever git ignores (`git ls-files --ignored --exclude-standard --directory`, run through `git_argv`/`git_env` so a target's own `.git/config` can't execute code). Each nested tree's own ignores are collected separately, because the parent's git can't see inside a submodule.
- Excluded: dot-directories at any depth, plus `__pycache__` and `node_modules` (`_skip_dir`, `_pruned_dirs`). Inside a nested tree only that tree's top-level dot-directories are kept, and the walk stops there.
- Depth is capped at 16. Directories past the cap are taken whole and recorded, not silently pruned.
- The `doxygen-guard` `files:` pattern is deliberately not read. That pattern answers what must be documented, not what should be indexed.
- If git is missing or the tree isn't a repository, the scope gets a warning and nothing is excluded. The result is wider, not empty.

**What happens with nothing declared:** `derive_scope` returns the whole-repo tier, and the reason string says so: "no index_scope is declared … so the whole repository is the index scope." The Doxyfile is not consulted for `INPUT`. It still supplies `ALIASES` and `PREDEFINED`.

**From scope to file set:** the doxygen stage enumerates the resolved roots. A Rust or JS/TS-only target has no Doxyfile, so `_scanned_files` in `clew/cli.py` (around line 2483) reads the exact `scope_result` the build applied. If nothing was declared, it falls back to `[repo_root]` with the same excludes.

**Refusal vs. fallback:** `derive_scope` absorbs a rejected declaration into the whole-repo tier so internal callers always get a scope. The CLI and the MCP refresh path call `declared_scope_rejection` first and refuse instead. The gh#5 and B12 incidents are why this split exists.

## This repository

`.clew.yaml` here has only a `guard:` section and no `index_scope:`, so the build uses the whole-repo tier.

## Discrepancies and gaps

- `docs/languages/C_INTEGRATION.md` (section "The three things that decide what gets indexed") still says `INPUT`, `EXCLUDE` and `FILE_PATTERNS` decide scope. That contradicts gh#333 and the code. The later paragraph in the same doc is correct.
- I did not trace `toolchain.toml` skips or operator excludes (`extra_exclude`) in detail. I only saw that `_scanned_files` applies `extra_exclude`.
- I did not read `doxygen_input_roots` or the exact Doxyfile-stage code, so I can't speak to how that stage filters beyond the scope roots and excludes.