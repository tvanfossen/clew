**Short answer:** the index's scope is decided by the repo's own `index_scope:` declaration in `.clew.yaml`. If there isn't one, the scope is the whole repository minus what git ignores and a few dot/cache directories. Several later filters then drop more files: binaries, `toolchain.toml` ignores, and doxygen's forced extension list. I read this from the code and did not run a build.

**The decision flow**

```
clew index <repo>
 │
 ├─ derive_scope()                        clew/scope.py:639
 │    ├─ .clew.yaml has index_scope:?
 │    │    yes → roots/excludes taken at face value (must be repo-relative, must exist)
 │    │    bad keys / no usable roots → _Rejected → whole-repo, with the reason logged
 │    └─ no index_scope → whole_repo_scope()                 scope.py:683
 │
 ├─ build_options: extra_input = scope.roots, extra_exclude += scope.excludes
 │                                                          cli.py:745
 ├─ operator --exclude, then toolchain.toml [ignore].paths and suppress.toml
 │                                                          cli.py:3112-3120
 ├─ enumerate_tree(roots, excludes)    treescan.py:203   prunes excluded dirs during the walk
 ├─ _drop_binary_files()               cli.py:2554, filetypes.py   classify_file → binary out
 └─ doxygen run with forced FILE_PATTERNS (doxygen.py:203) and EXCLUDE entries
```

**When nothing is declared (the default)**

`whole_repo_scope` makes the repo root the single root, and computes the excludes as follows:

1. **Git-ignored paths.** `git ls-files --others --ignored --exclude-standard --directory` at the root, and the same for every nested git tree, so a submodule's own `.gitignore` applies. If git fails, the ignore list is empty and a warning is logged. The scope then gets wider, and the code does not treat that as a silent success.
2. **Dot and cache directories.** Any directory named `.*`, `__pycache__` or `node_modules` is excluded. Nested git trees are descended into, so their `.git` stores are pruned too.
3. **Nested git trees are included, not cut out** (gh#333). They are indexed, and `external.py` tags their rows afterwards so two codebases can be told apart in an answer.
4. **Depth limit of 16.** Deeper directories are taken whole and recorded in `depth_limited_paths()`, so nothing is silently dropped.
5. **Log line.** `scope: indexing the WHOLE repository — no index_scope is declared…` is logged at WARNING.

Files are then filtered further:

- **Binaries** are removed by `lang_parsing_substrate.classify_file` before doxygen reads them. There is no size limit, so a large generated `.c` file is still read.
- **Doxygen's extension set.** `FILE_PATTERNS` is forced to doxygen's own default list (`*.c`, `*.h`, `*.py`, `*.md`, and so on), so a repo's Doxyfile cannot veto files the scope admitted (gh#340).
- **Other languages.** Rust and JS/TS files come from the same scanned tree (`_scanned_files`, cli.py:2483), so they follow the same scope.

**What this means for this repo**

`/…/self/repo/.clew.yaml` declares no `index_scope`, so the whole-repo default applies. Its `validate.exclude` block (`tests/`, `acceptance/`, `scripts/`) governs the **gate only**. `scope.py` says the gate is not read for scope, so those directories are still indexed. `git ls-files --others --ignored` returns nothing here and there are no submodules. The excluded set is therefore just `.git`, `.github` and `.claude-plugin`.

**Two things I noticed**

- **Declared scope does not apply `.gitignore`.** A declared root is "taken at its word and never walked". The gitignore and dot-directory pruning (`_gitignored_paths`, `_pruned_dirs`) run only in `whole_repo_scope`. So under `index_scope.roots: [src]`, a `build/` or `.venv/` inside `src` would be indexed unless the owner lists it in `excludes`. The docstring around `scope.py:939` says otherwise, so that comment is stale. I did not confirm this with a build. A check would be to declare a root containing an ignored directory and see whether its files appear in the index.
- **`_pruned_dirs` is O(whole tree).** On a repo with no declaration it walks every directory once to collect exclusions. That is a cost, not a correctness problem.