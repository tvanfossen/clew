Scope is decided by a declaration in the repo, and if there is none, by the whole repository minus what git ignores. A Doxyfile no longer decides which files are indexed.

**The decision path**

`derive_scope` in `clew/scope.py:639` is the single entry point. It resolves in two tiers:

1. **Declared scope.** `_declared_index_scope` (`clew/scope.py:991`) reads the `index_scope:` section of the repo's `.clew.yaml`. Roots are repo-relative, and each root is taken at its word and never walked. A root that does not exist on disk is dropped with a warning. `excludes` is optional, but `roots` is required. A scope that is present but unusable is rejected rather than treated as absent. Unknown keys inside `index_scope` are refused by name, so a misspelling like `exclude:` cannot silently do nothing.
2. **Whole repository.** If nothing usable is declared, `whole_repo_scope` (`clew/scope.py:683`) makes the repo root the single INPUT root. Its excludes are the paths git ignores, on both sides of every submodule boundary, plus dot and cache directories. Nested git trees (submodules, vendored clones) are included, not cut out.

**What "nothing declared" means**

- The Doxyfile is not a tier. Its `INPUT` is treated as a documentation target, not a reasoning boundary. The repo's Doxyfile is still read for `ALIASES` and `PREDEFINED`, but its `INPUT` is replaced.
- The doxygen-guard `files:` pattern is not a tier either. It governs what must be documented, not what gets indexed.
- A repo with no `index_scope:` therefore gets its whole tree, less git-ignored paths and dot or cache directories. The build log records the reason, including where the declaration was looked for.

**Two related points**

- `declared_scope_rejection` (`clew/scope.py:612`) is a separate build-time check. `derive_scope` absorbs a rejected declaration into the whole-repo tier so internal callers always get a usable scope. The CLI and MCP refresh paths call this check first and can refuse the build instead. This exists because an excludes-only declaration once let a build proceed into the widest scope under a vendored tree it was meant to exclude.
- Nested trees are tagged rather than excluded. `clew/external.py` marks files that sit inside a foreign git tree as external, so aggregates report first-party by default. Queries still traverse into them.

**Caveat**

The `C_INTEGRATION.md` section titled "The three things that decide what gets indexed" describes Doxyfile `INPUT`, `EXCLUDE` and `FILE_PATTERNS` as deciding scope. That reads as older than the gh#333 change. I only saw a snippet, so I have not confirmed whether `FILE_PATTERNS` still filters anything in the current build.