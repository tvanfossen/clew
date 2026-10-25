Two things decide what gets indexed: the repo's own `index_scope:` declaration in `.clew.yaml`, if it has one, and otherwise the whole repository minus what git ignores. A file also has to be in a language clew can parse.

**The decision, in order**

```
derive_scope(repo_root)                              clew/scope.py:639
 ├─ _declared_index_scope(root)                      scope.py:991
 │    reads .clew.yaml → index_scope: {roots, excludes}
 │    ├─ no section                    → None (fall through)
 │    ├─ bad shape / unknown key / no
 │    │  root that exists              → _Rejected (logged, then fall through)
 │    └─ valid                         → DerivedScope(source=declared)
 └─ whole_repo_scope(root)                           scope.py:683
      roots = (repo_root,)
      excludes = git-ignored paths + dot/cache dirs
```

1. **Declaration first.** `derive_scope` calls `_declared_index_scope`, which loads `.clew.yaml` through `load_declaration_located` (`clew/declaration.py:299`). That function returns the parsed mapping and the file it came from, and drops the `guard:` section because that belongs to the gate. Roots are repo-relative. A root that does not exist on disk is dropped. A declared root is taken at its word and never walked. The `roots` key is required; `excludes` alone does nothing.
2. **Failures fall through, but they are not silent.** A declaration that is present but unusable is logged as a WARNING with the reason and the build still proceeds on the whole-repo tier. A misspelled top-level section is different: `load_declaration_located` raises `DeclarationError` and refuses, because a section nothing reads would otherwise look honoured while the build uses defaults.
3. **Whole-repo default.** With nothing declared, the single root is the repository itself. The excludes are:
   - everything `git ls-files --others --ignored --exclude-standard --directory` reports, run with a sanitized git environment;
   - the ignored paths of each nested git tree, so a submodule's `.gitignore` counts;
   - dot-directories (any name starting with `.`) and `__pycache__` and `node_modules`, pruned by `_pruned_dirs`. The walk stops at nested git trees and at a depth limit (16 per the comment), and the walk does not descend below either.

   Nested git trees are included, not excluded. `external.py` tags their rows afterward so a vendored codebase can be told apart in an answer.
4. **Doxyfile no longer decides scope.** The old fallback that handed INPUT to the Doxyfile was removed (gh#333). A Doxyfile still supplies aliases and predefined macros, but not the file set.
5. **The file set the index publishes.** For a parse-built front end (Rust, JS/TS, or a build with no doxygen stage), `_scanned_files` in `clew/cli.py:2483` reads the `DerivedScope` the build actually applied and walks only inside its roots and excludes. With no declaration it walks `[repo_root]`. Extensions decide whether a file is parsed at all: a file whose extension no grammar handles is not indexed, so a large directory can be small in the index. The extension tables live in `harvest` and `synth`; I did not read their contents through the index.

**When nothing is declared**

The whole repository is indexed, less what git ignores and the dot and cache directories. The `reason` string on the scope says so and names where it looked for a declaration, then points to `propose_declaration` for narrowing it. In short, zero config means "everything git tracks or would track, minus ignored and dot paths, parsed by extension." The `index` tool's `scope` argument accepts `from-declaration`, which `normalize_scope` maps to the recorded `from-guard`. Unknown values are not mapped to a default; they are refused by the caller.

**Caveats**
- `load_declaration_located` came back with `anchor_mismatch: true`, so its line range may not match the current source. The behaviour above is from its docstring and the callers, not a verified read of the body.
- The depth limit of 16 comes from a comment next to `_MAX_DEPTH`; I did not dossier the constant itself.
- The extension tables and the `_skip_dir` rule come from test names and docstrings, not their bodies.