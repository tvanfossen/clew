Short answer: a declared `index_scope:` in the repo's `.clew.yaml` decides, and when nothing is declared the whole repository is indexed minus what git ignores and minus dot and cache directories. A Doxyfile does not decide the scope any more (gh#333). I read this from the index's docs and source for `clew/scope.py`, `clew/doxygen.py` and `clew/treescan.py`, not by running a build.

**Decision order (`derive_scope`, `clew/scope.py:639`)**

```
stated scope (tool-call argument)      ──► if present and usable, use it
  │ absent
.clew.yaml  index_scope:               ──► if present and usable, use it
  │ absent                                   (present but unusable → rejected)
whole repository (less ignores)        ──► the default
```

1. **Stated scope.** An operator can pass a scope at call time. `_declared_index_scope` builds it through the same path as a file declaration, so it is validated the same way.
2. **Declared scope.** `_declared_index_scope` (`clew/scope.py:991`) reads `index_scope:` from `.clew.yaml`. `roots:` is required and replaces the scope. `excludes:` subtracts from it. Roots that do not exist on disk are dropped. Unknown keys inside the block are refused by name, not ignored. A block with no usable root is marked rejected, and the reason says so.
3. **Whole repository.** `whole_repo_scope` (`clew/scope.py:683`) is the tier every repo gets for saying nothing. Its single root is the repo itself. Its excludes are:
   - everything `git ls-files --others --ignored --exclude-standard --directory` reports (`_gitignored_paths`, `:845`), run per repo and per nested git tree, so a submodule's own `.gitignore` applies;
   - dot-directories and `__pycache__` and `node_modules` (`_skip_dir`, `:490`), pruned by `_pruned_dirs` (`:908`), which does not descend into nested git trees beyond their top level.

Nested git trees (submodules, vendored clones) are indexed, not excluded. `external.py` tags their rows afterwards so answers can tell the codebases apart.

**What the Doxyfile and gate do now**

- The repo's Doxyfile still supplies ALIASES and PREDEFINED. Its `INPUT` is replaced, so a Doxyfile that documents only a header subset no longer narrows the index. The docs cite Mbed-TLS: its Doxyfile's `INPUT = ../include` would have indexed 1,571 header declarations and zero of the 108 `library/*.c` files.
- `FILE_PATTERNS` is forced to `DOXYGEN_DEFAULT_FILE_PATTERNS` (`clew/doxygen.py:203`, C/C++ extensions and similar). `effective_file_patterns` returns that set regardless of what the target's Doxyfile declares.
- The doxygen-guard `files:` pattern is explicitly not a tier. It answers what must be documented, not what should be indexed.

**When nothing is declared**

- The scope is the whole repository, less git-ignored paths and dot/cache directories. No Doxyfile is needed.
- The reason is logged: the build says no `index_scope` is declared and names where it looked. This is the "absence is not emptiness" rule in practice.
- If git is missing or the tree is not a repository, nothing is excluded and a warning says so. The index is wider than the repo asked for, but it still builds.

**Things I did not fully verify**

- `derive_scope` itself falls through to the whole repository when a declaration is rejected, with the rejection in the reason. The test `test_cli_apply_scope_refuses_a_rejected_declaration` says the CLI refuses the build instead. The refusal is probably decided before `derive_scope` is called (`declared_scope_rejection`), but I did not trace that path.
- I did not read `enumerate_tree` in `treescan.py`, which applies per-file matching during the walk. I also did not see the full `DOXYGEN_DEFAULT_FILE_PATTERNS` list, only its first entries.