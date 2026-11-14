**Short answer:** unless a repo declares an `index_scope:` in its `.clew.yaml`, clew indexes the whole repository. The only things removed are what git ignores, dot-directories and a few cache/vendor names. Doxygen then keeps only files matching its own default extension list. I read the source for this and did not run an index build, so the exact counts for a real repo are unverified.

**Decision sequence**

```
.clew.yaml present?
 ├─ no ───────────────────────────────┐
 ├─ yes, only guard: ─────────────────┤  (guard section is dropped; index sees nothing)
 ├─ yes, index_scope: usable ─► DECLARED scope (roots + excludes)
 └─ yes, index_scope: unusable ─► REJECTED ─► whole-repo, with reason
                                      │
                                      ▼
                    WHOLE REPO: roots=(repo root,)
                    excludes = git-ignored paths
                             + dot-dirs, __pycache__, node_modules
                    then Doxygen filters by FILE_PATTERNS
```

1. **Declaration read** (`declaration.py`, `load_declaration_located`). It reads `<repo>/.clew.yaml`. A missing or unparseable file is treated as absent and logged. An unknown top-level section is a hard refusal, so a typo cannot silently fall back to defaults. The `guard:` section is stripped before the index sees it, so a file that only configures the gate declares nothing to the index.

2. **Declared scope, if any** (`scope.py`, `_declared_index_scope`). The only scope-deciding key is `index_scope:` with `roots:` and `excludes:`. Roots are repo-relative and must exist on disk. A declared root is taken at its word and never walked. If `index_scope` is present but unusable (a non-mapping, an unknown key, or no existing roots), it is rejected with a reason. `derive_scope` then falls back to whole-repo and logs a WARNING. The CLI and MCP refresh path check for this rejection separately and refuse, rather than silently building the wider scope.

3. **Whole-repo fallback, the default** (`scope.py`, `whole_repo_scope`). This is what a repo gets by saying nothing, and since gh#333 it is the default rather than a last resort:
   - **Root:** the repository itself.
   - **Git-ignored paths:** `git ls-files --others --ignored --exclude-standard --directory`, run per repo. Nested trees (submodules and clones) are asked for their own ignores too, because the parent's `ls-files` stops at their boundary.
   - **Pruned directories:** any name starting with `.`, plus `__pycache__` and `node_modules`. The walk stops at depth 16 and records those directories rather than descending.
   - **Nested git trees are included,** not excluded. They are tagged as external afterwards in `external.py`, so `chain_trace` can say what a call does instead of stopping at a submodule boundary.
   - If the directory is not a git repo, nothing is git-ignored. A WARNING says so, and build outputs then get indexed.
   - A WARNING is logged: "indexing the WHOLE repository — no `index_scope` is declared …".

4. **Doxygen filtering.** Doxygen runs with `RECURSIVE=YES` over the chosen root. Its `INPUT` is replaced by that root, and `EXCLUDE`/`EXCLUDE_PATTERNS` are set from the excludes above. Its `FILE_PATTERNS` are forced to doxygen's own default list (`doxygen.py`, `DOXYGEN_DEFAULT_FILE_PATTERNS`), which covers C/C++, Java, C#, PHP, Python, Fortran, VHDL, Markdown and similar. A repo's own Doxyfile is still read, but only for `ALIASES` and `PREDEFINED`. Its `INPUT`, `FILE_PATTERNS` and `EXCLUDE*` are discarded, so a repo cannot narrow the index by documenting itself.

5. **Other languages.** Rust, JS/TS, shell and CMake files have no doxygen front end. Their extensions are routed in `harvest.py` and `synth.py` instead. I did not trace how each of those harvesters enumerates files, so I cannot confirm they use exactly the same scope roots and excludes.

**Things to check**

- `.clew.yaml`'s `guard.validate.exclude` (which skips `tests/`, `scripts/` and `acceptance/`) has no effect on the index. `scope.py` says so explicitly: the gate answers what must be documented, not what is reasonable to index. Those paths are indexed when nothing is declared.
- An `index_scope` that names only `excludes:` does nothing. `roots` is required.