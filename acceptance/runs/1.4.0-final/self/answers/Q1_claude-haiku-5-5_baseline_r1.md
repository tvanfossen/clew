**Short answer:** nothing filters by file type at the scope stage. The scope decides which *directories* are walked. Binary files are removed next. Each downstream parser then picks up only the languages it understands. With no declaration, the scope is the whole repository minus what git ignores, dot-directories and caches, and nested git trees are included.

**The chain, in order** (paths relative to the repo root):

```
derive_scope(root)                      clew/scope.py:639
 ├─ declared index_scope: in .clew.yaml?  → use its roots, minus its excludes
 │    (roots are taken at their word, never walked)
 └─ otherwise → whole_repo_scope(root)   clew/scope.py:683
      roots    = (repo root,)
      excludes = git-ignored paths
               + nested-repo ignores
               + dot-dirs and __pycache__/node_modules  (_pruned_dirs, :908)
            ↓
enumerate_tree(roots, excludes)         clew/treescan.py:203
      walks everything not excluded; no extension filter, by design
            ↓
_drop_binary_files                      clew/cli.py:2554 → clew/filetypes.py
      classifies each file by content (magic bytes, NUL/control ratios),
      not by extension; binaries are dropped and added to doxygen's excludes
            ↓
doxygen (INPUT = roots, EXCLUDE = excludes)
      reads only files matching DOXYGEN_DEFAULT_FILE_PATTERNS (clew/doxygen.py:203)
      C/C++, Java, C#, PHP, *.h, and so on
            ↓
tree-sitter harvest                     clew/harvest.py:184
      _ts_language_for(): C, C++, Python, Rust, CMake, by extension or name
```

**What decides membership.** Three things, in this order:

1. **Declaration.** An `index_scope:` section in `.clew.yaml` with at least one existing `roots:` entry replaces the whole-repo scope. `excludes` alone is rejected. Unknown keys are rejected too, and a rejected declaration falls back to the whole repo with a logged warning (`scope.py:612–675`).
2. **Git ignore plus structure.** Ignored files are excluded by `git ls-files --others --ignored --exclude-standard --directory` (`scope.py:845`). This includes untracked-but-ignored paths only. Tracked files that happen to match `.gitignore` are not excluded. Untracked files that are not ignored are included.
3. **Content and language.** Binaries are dropped by content sniffing. Parsing is then decided per consumer: doxygen by its FILE_PATTERNS list, tree-sitter by grammar extension.

**What happens when nothing is declared.** This is the default, and this repo is an example. Its `.clew.yaml` configures only `guard:` and `validate:` and has no `index_scope:`, so the comment in that file says the index "builds this repo on its defaults". In that case:

- The scope is the whole repository, including nested git trees (gh#333). Those trees are tagged by `external.py` so their rows can be told apart in answers.
- Git-ignored paths, dot-directories such as `.git`, `.venv`, `.claude` and `.github`, plus `__pycache__` and `node_modules`, are excluded.
- The Doxyfile does not set the scope. Its INPUT is ignored. Its ALIASES and PREDEFINED still apply.
- The walk stops at a depth of 16. Below that it takes the tree wholesale and logs a warning.
- The reason string recorded in the build log says that no declaration was found and the whole repository was used. It also suggests how to declare a narrower scope.

**Consequence worth knowing.** On an undeclared repo, anything not gitignored gets indexed, including scratch files, generated output not listed in `.gitignore`, and vendored code. The only guard is the binary sniff. A narrower scope requires a declaration.

I did not run an index build to confirm the file counts. The description above is from reading the code paths.