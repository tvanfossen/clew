**Short answer:** clew indexes whatever the repo's own `.clew.yaml` `index_scope:` declares. If nothing is declared, it indexes the whole repository, minus what git ignores and minus dot and cache directories. A Doxyfile no longer decides scope.

**Decision order** (`clew/scope.py`, `derive_scope` at line 639)

```
derive_scope(repo_root)
 ├─ _declared_index_scope(root)          reads .clew.yaml → index_scope:
 │    ├─ no index_scope section   → None  → falls through
 │    ├─ rejected (bad shape/keys,
 │    │   no usable roots)        → _Rejected → WARNING, whole repo, reason says why
 │    └─ usable                   → DerivedScope(source=DECLARED, roots, excludes)
 └─ whole_repo_scope(root)               the default tier
```

**When a declaration exists**

- `.clew.yaml` lives at the repo root. `load_declaration_located` (`clew/declaration.py:299`) reads it.
- `roots` is required and is repo-relative. A root that does not exist on disk is dropped with a warning. If no root survives, the declaration is rejected.
- `excludes` is optional. It cannot stand alone.
- Unknown keys inside `index_scope:` reject the declaration. An unknown top-level section refuses the build outright, so a typo never silently falls back to defaults.
- Declared roots are taken at their word and never walked. A clone nested under a declared root is indexed without being noticed. `external.py` tags those rows afterwards so two codebases can still be told apart.

**When nothing is declared (`whole_repo_scope`, line 683)**

This is the default tier since gh#333. The root is the whole repository, with these subtractions:

1. Paths git ignores. `git ls-files --others --ignored --exclude-standard --directory` runs on the root and on every nested git tree, since a submodule's own `.gitignore` is invisible to the parent.
2. Dot-directories and `__pycache__` / `node_modules`, found by `_pruned_dirs` and `_skip_dir`. These are not walked into nested trees below their top level.
3. A walk-depth guard at 16 levels. Directories past it are taken whole and recorded, so the index can report where the walk stopped.

Nested git trees are included, not excluded. The doxygen-guard `files:` pattern and the `guard:` section play no part. The reason string attached to the scope names the absence of a declaration, the rejection if there was one, and the `propose_declaration` advice.

**Degenerate cases**

- A malformed or unreadable `.clew.yaml` is logged at WARNING and treated as absent, so the build falls back to the whole repository.
- Not a git repository, or git missing: no ignore subtractions. The build logs that and indexes a wider tree.
- A Doxyfile, if present, still supplies ALIASES and PREDEFINED. Its INPUT is replaced by the derived roots. The Mbed-TLS example in the module docstring shows why: honouring a docs-oriented INPUT indexed headers and skipped `library/*.c`.

**Where the scope goes**

- Doxygen gets the roots as INPUT and the excludes as EXCLUDE.
- For Rust and JS/TS targets, which have no doxygen enumeration, `_scanned_files` (`clew/cli.py:2483`) walks the same roots with the same excludes. It reads the scope the build actually applied, not a fresh derivation.

**Caveats**

- The `scope.py` file itself is not resolvable through `dossier` by path, so I read it directly. Its symbols are indexed.
- `load_declaration_located` came back with `anchor_mismatch: true`, so its body may not match the current file. I took its behaviour from the docstring and did not re-verify the code.