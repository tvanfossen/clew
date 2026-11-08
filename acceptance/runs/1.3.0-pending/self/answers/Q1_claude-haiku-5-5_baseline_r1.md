**Short answer:** with nothing declared, the index scope is the whole repository minus what git ignores, minus dot-directories and a few cache/vendor names. That candidate set is not filtered by extension. Which of those files get parsed is decided later, by Doxygen's forced `FILE_PATTERNS` and by per-language front ends. This is from reading the code; I did not run a build.

**The decision, in order**

1. **Default scope is `from-guard`.** `cli.py:348` sets it. Despite the name, it no longer reads the gate. It reads `index_scope:` from `.clew.yaml`, and falls back to the whole repo when that is absent.

2. **Declaration check (`scope.py:639`, `derive_scope`).** It looks for `index_scope:` with `roots` and `excludes`. This repo's `.clew.yaml` has none; its header says the index "declares nothing here and builds this repo on its defaults." A present but unusable declaration is refused at build time (`cli.py:807`), not silently replaced.

3. **Whole-repo tier (`scope.py:683`, `whole_repo_scope`).**
   - Root: the repository itself, including nested git trees. Those are indexed and tagged later, not cut out.
   - Excludes, from three sources:
     - `git ls-files --others --ignored --exclude-standard --directory` (`scope.py:845`), so `.gitignore` is the main filter. The git call uses `git_argv`/`git_env`, so the target's own `.git/config` cannot run code.
     - The same query run inside each nested tree.
     - Dot-directories and `__pycache__`/`node_modules` (`_skip_dir`, `scope.py:490`), pruned in a walk that stops at nested trees (`_pruned_dirs`).
   - If the tree is not a git repo, nothing is ignored and a warning says so. The index is then wider than the repo asked for.

4. **Toolchain exclusions (`cli.py:2523`).** A `toolchain.toml` `[ignore].paths` entry is folded into the same exclude list. This repo has no `toolchain.toml`, so this step does nothing here.

5. **Enumeration (`treescan.py`, `enumerate_tree`).** It walks the roots, pruning excluded subtrees, and keeps every regular file. There is no extension filter. Files are hashed for cache identity, so any change forces a re-run.

6. **Binary removal (`cli.py:2554`, `filetypes.py`).** `classify_file` drops binaries before anything reads them. Empty files and large generated sources stay in.

7. **Doxygen reads only its forced `FILE_PATTERNS` (`doxygen.py:203–270`).** Doxygen's full default list is forced, so a declared `FILE_PATTERNS` cannot narrow it. It covers C/C++, Java, Python, Fortran, Markdown and others. A declared Doxyfile contributes ALIASES and PREDEFINED only; its `INPUT` is replaced (`doxygen.py` around line 783). Without a Doxyfile, one is synthesized.

8. **Other languages come from their own front ends, not Doxygen.** Tree-sitter (`harvest.py`) handles Python, Rust, C/C++, JS/TS, shell and CMake. `synth.py` claims JS/TS, shell, CMake and YAML/JSON. YAML/JSON are registered as `path` rows but harvested for no symbols.

**What "nothing declared" means in practice**

| Situation | Result |
|---|---|
| Ignored by `.gitignore` | Not indexed |
| Dot-dir or `__pycache__`/`node_modules` | Not indexed, anywhere in the tree |
| `.venv`, `build/` not in `.gitignore` | Indexed (only dot-dirs are pruned by name) |
| Binary file | Dropped and logged at INFO |
| Source file of a type nothing claims (e.g. `.txt`) | Enumerated and hashed, but no `path` row |
| Scanned but not in the `path` table | Reported in `not_indexed` / `not_indexed_count` (`cli.py` around 2660) |

The `not_indexed` report is the place to check for silent gaps. It counts files that were in scope but produced no row.

**Caveat on tool output:** several of my file reads returned trailing text suggesting I call a clew `dossier` tool instead. That is not part of your question, so I ignored it and read the source directly.