The short answer: a repository's own `index_scope:` declaration is the only thing that narrows the index. With no declaration, clew indexes the whole repository minus what git ignores and a few cache and dot directories. The Doxyfile does not decide scope anymore. I read `clew/scope.py` directly for this, because the index's copy of it is flagged as anchor-mismatched.

**Decision path**

```
build starts
  └─ derive_scope(repo_root)                          clew/scope.py:639
       ├─ _declared_index_scope(root)                 clew/scope.py:991
       │    ├─ no index_scope: section      → None → whole-repo tier
       │    ├─ section not a mapping        → _Rejected → whole-repo tier (reason kept)
       │    ├─ unknown key inside section   → _Rejected → whole-repo tier (reason kept)
       │    ├─ no existing roots:           → _Rejected → whole-repo tier (reason kept)
       │    └─ roots exist                  → DerivedScope(SOURCE_DECLARED, roots, excludes)
       └─ whole_repo_scope(root)                      clew/scope.py:683
            roots    = (repo_root,)
            excludes = git ignored paths
                     + paths ignored inside each nested git tree
                     + dot dirs and __pycache__/node_modules   (_pruned_dirs, :908)
                     + walk stops at 16 levels               (_MAX_DEPTH)
```

Then `derive_scope_logged` (`clew/scope.py:1313`) logs the outcome. A declared scope logs its roots at INFO. The whole-repo default logs a WARNING saying why the boundary was not chosen.

**What a declaration does**

- The shape is `index_scope: {roots: [...], excludes: [...]}`. Roots are repo-relative and taken at face value. They are never walked, so a clone nested under a declared root is indexed too.
- `roots` is required. `excludes` alone does nothing, and the code rejects it with an explanation rather than silently widening the scope.
- Unknown keys are rejected, which closes a gh#5 case where `exclude:` parsed fine and was never read.
- A root that does not exist on disk is dropped with a warning.
- A rejected declaration still produces a whole-repo index. The reason is logged so the WARNING does not claim nothing was declared. A test says the CLI apply path refuses a rejected declaration outright (`tests/test_scope.py`). I did not trace that path.

**What happens when nothing is declared**

- `_declared_index_scope` returns None, so `derive_scope` falls to `whole_repo_scope`. The single root is the whole repo, nested submodules included.
- What gets subtracted is what git already says is ignored, on both sides of every submodule boundary. `git ls-files --ignored --others --exclude-standard --directory` runs in the root and in each nested tree. Git's `core.fsmonitor` is blocked by using `git_argv`, so a cloned repo cannot run code through its own config.
- Dot-directories and `__pycache__`/`node_modules` are pruned as a traversal guard, not as a scope decision.
- The whole-repo reason string names the paths it looked for a declaration in, and says a Doxyfile does not supply the INPUT.
- If git is missing or the tree is not a repo, nothing is excluded and a warning is logged. The index is wider, not narrower.

**Doxygen's part**

Doxygen only parses what the scope hands it. Its INPUT is replaced with the derived roots, and the repo's own EXCLUDE and FILE_PATTERNS are cleared. `DOXYGEN_DEFAULT_FILE_PATTERNS` (`clew/doxygen.py:203`) is forced, so the default C/C++/Java/header extension list applies. The repo's own Doxyfile is still read for ALIASES and PREDEFINED. I did not check how the Python side gets its file set. It is parsed by the Python router, not doxygen.

**Stale comment to fix**

The docstring of `_declared_index_scope` (`clew/scope.py:1005`) still says a missing declaration "drops the resolution to the Doxyfile's own INPUT." That contradicts the gh#333 code, which falls back to the whole repository. The code is right and the docstring is wrong. Other index entries for `treescan.py` also show anchor mismatches, so their line numbers may be stale.