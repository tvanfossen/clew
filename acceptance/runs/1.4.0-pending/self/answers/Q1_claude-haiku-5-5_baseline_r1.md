**Short answer:** unless the repo declares an `index_scope:` in its `.clew.yaml`, clew indexes the whole repository minus what git ignores, dot-directories, and a few cache/vendor directories. Nested git trees are included and tagged, not excluded. I traced this by reading the code; I did not run a build.

**Decision flow**

```
clew index <repo>
  │
  ├─ cli._apply_scope / derive_scope_logged            (clew/cli.py:753, scope.py:1313)
  │     │
  │     ├─ .clew.yaml has index_scope: with roots: ?   ── yes ─→ DerivedScope(source=clew-declaration)
  │     │       (roots are taken at their word; missing roots dropped)
  │     │
  │     ├─ index_scope present but unusable?            ── CLI refuses (exit 1)
  │     │       (no roots, unknown key, not a mapping)     derive_scope alone falls back to whole-repo
  │     │
  │     └─ nothing declared (the default)               ── whole_repo_scope(repo)
  │             root = repo, excludes = git-ignored paths
  │                  + dot-dirs and __pycache__/node_modules
  │                  + nested-repo ignores
  │
  ├─ enumerate_tree(roots, excludes)    walks, prunes excluded subtrees, NO extension filter
  │
  ├─ Doxygen (C/C++/Java/Python/MD/… ) reads files matching FILE_PATTERNS
  │       FORCED to Doxygen's own default list, not the repo's Doxyfile
  │
  └─ tree-sitter harvesters (Python, Rust, JS/TS, shell, CMake)
          route by extension via _TS_GRAMMARS in harvest.py; other files get no rows
```

**What decides it, in order**

1. **Declaration (the only real decision).** `index_scope: {roots: [...], excludes: [...]}` in `.clew.yaml` is the one tier that states an index boundary. `roots` is required; `excludes` alone is rejected at the CLI because it does nothing. Unknown keys are rejected too.
2. **Whole repo (the default).** This is the zero-config path since gh#333. Doxygen's `INPUT` is replaced by the repo root. A repo's own Doxyfile still supplies aliases and predefines, but no longer its `INPUT`. The `guard:` section is the gate's and is ignored by the index.
3. **Exclusions in the default path.** Git-ignored paths come from `git ls-files --ignored --exclude-standard --directory`. Dot-directories and `__pycache__`/`node_modules` are pruned. Directories deeper than 16 are taken whole with a warning. If the directory is not a git repo, nothing is git-excluded and a warning says so, so the index is wider than intended.
4. **Extension filtering comes after scope.** `enumerate_tree` deliberately does not filter by extension, so the incremental cache hashes every in-scope file. Doxygen then applies the forced `FILE_PATTERNS` list (C/C++, Java, Python, Markdown, Fortran, and so on). The tree-sitter layers route by extension. A file that matches no pattern is walked and hashed but produces no rows.

**Unresolved:** I did not check `toolchain.toml` skips, which `AGENTS.md` mentions. The default tier and `test_scope.py:130` (`test_no_declaration_yields_the_whole_repo`) are the places to verify the behaviour; I did not run them.