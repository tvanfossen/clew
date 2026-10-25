Nothing is decided by a file-type whitelist at the scope level. The scope decision is made from the repo's declaration, and when there is none, clew indexes the whole repository minus what git ignores and a few cache directories. The rest of the filtering happens after that.

**How the decision is made**

1. **Read the declaration.** `load_declaration_located` (`clew/declaration.py:297`) reads `.clew.yaml` at the repo root. The `guard:` section belongs to the gate and is dropped, so a file that only configures the gate declares nothing to the index. A missing file is normal. A malformed file logs a warning and is treated as absent. An unknown top-level section refuses the build.

2. **Use `index_scope:` if it is usable.** `derive_scope` (`clew/scope.py:639`) calls `_declared_index_scope` (`scope.py:991`). That accepts only `roots` and `excludes`. Roots are taken at their word and never walked. Roots that don't exist are dropped. If the section is present but unusable, for example it has no roots or an unknown key, it is rejected with a reason and the build falls back to the whole repo with a warning. It does not silently widen the scope.

3. **Otherwise, whole repo.** `whole_repo_scope` (`scope.py:683`) is the default. The Doxyfile no longer supplies INPUT; that fallback was removed in gh#333. The single root is the repo, minus:
   - paths git ignores, from `git ls-files --others --ignored --exclude-standard --directory` (`scope.py:845`), applied to the root and to each nested git tree;
   - any directory whose name starts with `.`, plus `__pycache__` and `node_modules` (`_skip_dir`, `scope.py:490`), pruned by `_pruned_dirs`.

   Nested git trees are indexed and tagged as external rather than cut out.

4. **Walk and filter.** `enumerate_tree` (`clew/treescan.py:203`) walks the roots and prunes excluded subtrees during the walk. It is deliberately not filtered by extension. `toolchain.toml` `[ignore].paths` are folded into the excludes (`cli.py:2523`).

5. **Drop binaries.** `_drop_binary_files` (`cli.py:2554`) classifies what remains through `classify_file` (`clew/filetypes.py`). Binaries go into the exclude list before doxygen runs, and each one is logged at INFO. Size is not limited.

6. **Doxygen's pattern list.** For the doxygen-harvested languages, doxygen applies a forced `FILE_PATTERNS` set (`clew/doxygen.py:203`). That set is doxygen's own default, covering C/C++, Java, Python, Fortran, Markdown and similar. A declared `FILE_PATTERNS` no longer vetoes files (gh#340). The list contains no `.rs`, `.js` or `.ts`. Those files go through the parse-built front end via `_scanned_files` (`cli.py:2483`). I did not trace that path in full.

**What happens when nothing is declared**

Indexing proceeds on the whole repo with no error or refusal. `derive_scope_logged` (`scope.py:1313`) logs a WARNING: `scope: indexing the WHOLE repository — <reason>`. The reason names where it looked for a declaration and gives the exact `index_scope:` line to add. Every build logs its scope, so a boundary nobody chose is visible in the log.

This repo is a live example. Its `.clew.yaml` declares only `guard:` and states in a comment that the index "declares nothing here and builds this repo on its defaults."

**Caveats**

This is from reading the code. I did not run a build to confirm the resulting file set. I also did not trace the non-doxygen front end for Rust and JS/TS in detail.