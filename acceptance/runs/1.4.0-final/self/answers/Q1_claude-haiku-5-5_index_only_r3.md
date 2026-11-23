The short answer: a declaration decides the **roots** (directories the index walks), and doxygen's fixed file-pattern set decides which files inside them get parsed. With no declaration, clew indexes the whole git repository, minus git-ignored paths and dot/cache directories. Nothing in the index is extension-filtered by a user setting. I answered from the index alone. Its `propose_declaration` tool needed permission I didn't have, so I could not check its proposed draft.

**The decision chain**

```
.clew.yaml (index_scope:)          derive_scope()  clew/scope.py:639
        │                                 │
        ├─ usable roots? ── yes ──► DerivedScope(roots = declared, excludes = declared)
        │                                 │
        ├─ present but rejected ──► whole_repo_scope(rejected=<reason>)   (internal callers)
        │      └─ CLI --scope from-guard: refuses (sys.exit 1) instead      cli.py:758
        │
        └─ absent ──────────────────► whole_repo_scope(root)              scope.py:683
                                              │
                                              ▼
                       doxygen INPUT = roots; EXCLUDE = excludes
                                              │
                                              ▼
                 FILE_PATTERNS = DOXYGEN_DEFAULT_FILE_PATTERNS (forced)  doxygen.py:279
                                              │
                                              ▼
                 enumerate_tree() walks roots, prunes excluded subtrees  treescan.py:203
```

**1. Declared scope.** `_declared_index_scope` (`scope.py:991`) reads the `index_scope:` section from `.clew.yaml` (`declaration.py:299`). The section takes `roots:` and `excludes:`, and `roots` is required. A root that does not exist on disk is dropped with a warning. The section is rejected, not silently used, when:
- it is not a mapping;
- it has a key other than the accepted ones (a typo like `exclude:` for `excludes:` is refused by name);
- no root survives, so `excludes` alone does nothing.

An unknown top-level section in `.clew.yaml` also refuses the load, rather than degrading to defaults.

**2. Nothing declared.** `derive_scope` falls through to `whole_repo_scope` (`scope.py:683`). That function is explicitly "the default tier since gh#333, not the last resort":
- Its single root is the repository itself, nested git trees included.
- It subtracts what `git ls-files --others --ignored --exclude-standard --directory` reports, per tree, so a submodule's own `.gitignore` also counts. The git call runs through `gitenv.git_argv`, so a target's `.git/config` cannot execute code.
- It subtracts dot-directories and known cache/vendor names via `_skip_dir` (`scope.py:490`), pruned by `_pruned_dirs` (`scope.py:908`). Those become doxygen `EXCLUDE` entries because the root is handed to doxygen unwalked. Its reason string says no `index_scope` was declared and names where `.clew.yaml` was looked for.
- A repo's own Doxyfile no longer supplies INPUT. It still supplies aliases and predefined macros.
- The warning "indexing the WHOLE repository" is logged at WARNING level (`derive_scope_logged`, `scope.py:1313`).

**3. Which files doxygen parses.** The `FILE_PATTERNS` list is not declarable. `effective_file_patterns` (`doxygen.py:279`) returns the forced `DOXYGEN_DEFAULT_FILE_PATTERNS` for every build, so a target's declared patterns are only reported, not applied. `enumerate_tree` (`treescan.py:203`) is deliberately not extension-filtered. It hashes every file under the roots so that any change forces a re-run.

**4. Stated scope.** A caller's own `index_scope` (for example a vendored sub-index override) is treated as tier 1 and takes the same construction path as a written one, so it can't behave differently from a file-declared one.

**Caveats**
- I verified the scope logic from function bodies and tests, not the contents of `_SKIP_DIR_NAMES` or `DOXYGEN_DEFAULT_FILE_PATTERNS`. Those lists are the answer to "which dot/cache dirs and which extensions", and I did not read them.
- The `load_declaration_located` dossier reported an anchor mismatch, so its line numbers may be stale.
- Nested git trees are indexed by design, and `external.py` tags their rows so they can be told apart from the first-party code.