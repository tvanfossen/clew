**Short answer:** the index is built from one resolved "scope", a set of INPUT roots plus EXCLUDE patterns, which `clew/scope.py:derive_scope` picks from a declaration in `.clew.yaml`. If nothing usable is declared, the whole repository becomes the scope, minus what git ignores and a fixed set of dot and cache directories. The Doxyfile no longer decides the file set.

**The decision, in order**

```
build starts
  └─ derive_scope(repo_root)                       clew/scope.py:639
       ├─ _declared_index_scope()                  clew/scope.py:991
       │    ├─ no index_scope: section  → None      (fall through)
       │    ├─ bad shape / unknown key / no
       │    │   usable roots             → _Rejected (logged WARNING, then fall through
       │    │                                        with the rejection as the reason)
       │    └─ roots exist              → DerivedScope(source=declared)
       └─ whole_repo_scope(root)                    clew/scope.py:683   ← the default tier
  └─ _fold_scope_into_args()                        clew/cli.py:739
       sets extra_input = scope.roots, extra_exclude = scope.excludes, replace_input = True
  └─ doxygen runs over those roots
```

1. **Declared scope (tier 1 or 2).** `.clew.yaml` (`CONFIG_FILE_NAME`, `clew/guard/config.py:29`) may carry an `index_scope:` with `roots:` and `excludes:`. Roots are taken at their word and never walked. Roots that do not exist on disk are dropped. `roots:` is required, so `excludes:` alone does nothing. Unknown keys inside the section are refused by name rather than ignored. A declared root that contains a nested git clone gets that clone indexed too, and `external.py` tags its rows so the two codebases can be told apart in answers. A caller can also state a scope on the tool call, which is treated like a declaration with a different "reason" string.

2. **Whole-repo default (tier 3).** `whole_repo_scope` is labelled "THE DEFAULT TIER since gh#333, not the last resort". It is used when there is no `index_scope:`, or when the declared one is rejected. Its single root is the repo root. Its excludes are:
   - paths git ignores, read per tree, including inside nested git trees (their `.gitignore` is invisible to the parent);
   - dot-directories and `__pycache__` / `node_modules` (`_SKIP_DIR_NAMES`, `clew/scope.py:57`), walked by `_pruned_dirs`, which stops at nested git trees and at `_MAX_DEPTH = 16` (`clew/scope.py:62`). Hitting the depth limit logs a warning and records the directory in `_DEPTH_LIMITED`.

   Nested git trees are indexed, not excluded.

3. **What does not decide the set.** A Doxyfile's `INPUT` no longer supplies the roots (`clew/scope.py:683` docstring; `clew/declaration.py:205`). Its `FILE_PATTERNS` are replaced by clew's own list (`clew/doxygen.py:270`, `DOXYGEN_DEFAULT_FILE_PATTERNS`). The Doxyfile still contributes aliases and predefined macros. The quality gate's `doxygen-guard` settings are also not read here, because they say what must be documented, not what should be indexed.

**What happens with nothing declared**

The build still runs and indexes the whole tree minus the subtractions above. Its `reason` string says that no `index_scope` was declared and names where it looked, and it adds advice to declare one in `.clew.yaml`. The scope decision is stored in build metadata, so `status` and empty query answers can state what was covered. The point of that reason string is that a fallback scope says the boundary was not chosen.

**Caveats**

- I could not run `propose_declaration` because the permission was not granted, so I have not checked what it would suggest for this repo.
- I read the exclusion and file-pattern details from function bodies and comments, not from a run against a sample repo. The `_SKIP_DIR_NAMES` and depth values are the ones in the source at the time of this index build.