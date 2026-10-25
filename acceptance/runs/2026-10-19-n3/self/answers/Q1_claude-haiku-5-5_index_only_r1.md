The index decides scope in one place, `derive_scope` in `clew/scope.py`, and it has two tiers. A declaration wins if one is usable. If not, the whole repository is the scope. The Doxyfile no longer chooses the file set.

**How the decision is made**

```
stated by caller (MCP/CLI options)     -> _declared_index_scope(stated)
        | none usable
        v
index_scope: in .clew.yaml             -> _declared_index_scope(root)
        | absent or rejected
        v
whole_repo_scope(root)                 -> the default
```

1. **Declared scope.** `_declared_index_scope` reads an `index_scope:` section with `roots:` (required) and optional `excludes:`. Roots are repo-relative, and a root that does not exist on disk is dropped. Roots are taken at their word and never walked. Clones nested under a declared root are indexed and tagged by `external.py` rather than excluded.
2. **Rejection.** A section that is present but unusable is rejected, not silently ignored. Examples: a non-mapping section, unknown keys (a typo like `exclude:` for `excludes:` is caught), or no usable `roots:` (excludes alone do nothing). `derive_scope` logs a WARNING and falls back to the whole repo. The MCP refresh path and the CLI call `declared_scope_rejection` first, so they can refuse the build instead of falling back.
3. **Stated scope.** Options passed by a caller are treated as a declaration: they go through the same construction, with a different `reason` string. Operator-stated excludes are carried separately and applied on top.

**What happens when nothing is declared**

`whole_repo_scope` returns one root, the repository itself, minus these subtractions:

- Paths git ignores, read per tree. The parent's `git ls-files` cannot see inside a submodule, so each nested repo's own `.gitignore` is asked separately.
- Nested git trees are included, not cut out. The earlier containment pass was removed (gh#333). Their rows are tagged afterwards.
- Dot-directories and cache directories are pruned.
- The walk does not descend into nested trees except to prune them.

The doxygen-guard gate is deliberately not consulted for scope. It answers what must be documented, not what should be indexed.

A Doxyfile, if the repo ships one, still supplies `ALIASES` and `PREDEFINED`. Its `INPUT` is no longer used as the boundary. The reason string for this tier says so, and it also names the file it looked for a declaration in. A repo with no Doxyfile and no declaration is still indexable (there is a test for it). `--scope from-guard` is the default, so a bare invocation indexes the whole repo.

**Caveats**

- The `index` tool does not expose the file list, so I could not check which individual files ended up in a given build. The answer is from the scope code and its tests.
- `docs/languages/C_INTEGRATION.md` ("The three things that decide what gets indexed") still describes `INPUT`/`EXCLUDE`/`FILE_PATTERNS` as independent scope levers. That predates gh#333, and the code now says the Doxyfile is not a reasoning boundary. Treat the doc as stale on this point.
- I did not confirm whether `FILE_PATTERNS` (an extension filter) still applies under the whole-repo tier. The code I read adds no extension filter, so this is an open question.