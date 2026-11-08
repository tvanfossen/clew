Nothing in clew's index is chosen by file extension. The file set is decided by one scope resolution, and with no declaration that resolution is "the whole repository, minus what git ignores and a few cache/dot directories."

**Decision flow**

```
clew build --scope from-guard (the default)
  └─ cli._apply_scope                        clew/cli.py:758
       └─ scope.derive_scope(repo_root)      clew/scope.py:639
            ├─ _declared_index_scope         clew/scope.py:991
            │    reads .clew.yaml → index_scope:
            │    ├─ no section → None → fall through
            │    ├─ bad section → _Rejected → build REFUSES (exit 1)
            │    └─ roots/excludes → DerivedScope(source=declared)
            └─ whole_repo_scope              clew/scope.py:683   (no declaration)
                 roots    = (repo_root,)
                 excludes = git-ignored paths
                          + nested-repo ignores
                          + dot dirs and __pycache__/node_modules
       └─ _fold_scope_into_args → INPUT list
  └─ treescan.enumerate_tree(roots, excludes)   clew/treescan.py:203
       walks every file under roots, drops anything under an exclude
       (no extension filter, by design)
```

**Declared case.** Tier 1 is `index_scope:` in the repo's `.clew.yaml`. It takes `roots:` (required, repo-relative, must exist on disk) and `excludes:`. The only keys accepted are `roots` and `excludes`. Any other key, or an `excludes:` with no `roots:`, is rejected by name rather than ignored. A rejected declaration makes the build exit 1 instead of quietly widening to the whole repo. A declared root is taken as written and never walked. The one exception is that nested git trees inside it are tagged later by `external.py`, not excluded.

**Undeclared case.** This is the default tier since gh#333. The scope is:

- **Root:** the whole repository, including nested git trees (submodules and vendored clones).
- **Git-ignored paths:** `git ls-files --others --ignored --exclude-standard --directory`, run on the root and on each nested tree separately. A submodule's own `.gitignore` is invisible to the parent, so it is asked separately.
- **Dot and cache directories:** any directory whose name starts with `.`, plus `__pycache__` and `node_modules`, pruned at each level. Nested trees are entered only for their own top-level dot directories.
- **Depth cap:** the walk stops at a fixed depth (16 per the source comment) and records where it stopped.
- **Not read:** the Doxyfile's `INPUT`, `FILE_PATTERNS` and `EXCLUDE` no longer decide scope. The doxygen-guard `files:` pattern is also not read, because it answers what must be documented, not what should be indexed. The Doxyfile still supplies `ALIASES` and `PREDEFINED`.

If the directory is not a git repository, or git is missing, no ignores are applied. The build logs a warning and the scope is wider than the repo asked for.

**Other inputs.** The operator's `--exclude` and the `toolchain.toml` skips also feed the walk, and binaries are classified downstream. I did not trace the toolchain or binary path in this pass, so treat those as unverified here.

**Stale documentation.** `docs/languages/C_INTEGRATION.md` (section "The three things that decide what gets indexed") still says the Doxyfile's `INPUT`, `EXCLUDE` and `FILE_PATTERNS` each decide scope. The code and its own precedence sentence say otherwise since gh#333. That section is out of date.