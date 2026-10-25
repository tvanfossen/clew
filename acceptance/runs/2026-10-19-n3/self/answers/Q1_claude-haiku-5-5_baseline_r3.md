The short answer: a declaration in `.clew.yaml` decides the scope if it is usable. If not, the whole repository is the scope, minus what git ignores and a few directory names. Two later filters then decide which of those files doxygen actually reads.

**1. Scope resolution (`clew/scope.py`)**

```
derive_scope(repo_root)
 ├─ .clew.yaml has index_scope: with usable roots?  → DerivedScope(source=declared, roots, excludes)
 ├─ index_scope present but unusable?               → log WARNING, fall to whole-repo, with the reason
 └─ no index_scope                                  → whole_repo_scope(root)
```

- **Declared scope.** `roots` is required. `excludes` alone is rejected, because the code says it "does nothing". Unknown keys in `index_scope` are rejected. Each path is resolved and must stay inside the repo, so absolute or `../` entries are dropped with a warning. Entries that do not exist are dropped too (`_existing_paths`). A declared root is taken at its word and never walked.
- **Whole-repo scope (the default since gh#333).** The root is the repository itself. Excludes are:
  - Git-ignored paths, from `git ls-files --others --ignored --exclude-standard --directory`. Each nested git tree's own ignores are collected separately, because the parent's listing stops at a submodule boundary.
  - Dot-directories (`.git`, `.venv`, `.claude`, …) and `__pycache__` / `node_modules`.
  - Nested git trees are *not* excluded. They are indexed and tagged external later (`external.py`).
  - The walk stops at depth 16 and records the directories it refused to descend into.
- **The Doxyfile is not a scope tier.** Its `INPUT`, `EXCLUDE` and `FILE_PATTERNS` are replaced. It still supplies `ALIASES` and `PREDEFINED`.
- **The `guard:` section is not read by the index.** The gate's `validate.exclude` list does not shrink the index. For this repo, `tests/`, `scripts/` and `acceptance/` are all indexed.

**2. From scope to a file list (`clew/treescan.py`, `clew/cli.py`)**

- `enumerate_tree` walks each root and prunes excluded subtrees during the walk. It does not filter by extension, so the content hash covers every surviving file.
- `_drop_binary_files` runs `lang_parsing_substrate.classify_file` on each file. Binaries are removed from the tree and added to the doxygen exclude list. Text files of any size are kept.
- Doxygen then runs with a forced `FILE_PATTERNS` set (gh#340). It is Doxygen's own default list, covering C/C++, Java, Python, Fortran, VHDL, Markdown and similar. A file whose extension is not in that list is not read by doxygen.
- JS and TS files are not read by doxygen. A parse-built front end registers them from the scanned file list instead (`treescan.py` around line 333).

**3. What happens when nothing is declared**

Nothing is narrowed. The whole repository is the root, less git-ignored paths and dot/cache directories. Nested clones and submodules are indexed and tagged. The build logs `scope: indexing the WHOLE repository — no index_scope is declared for this repo — …` at WARNING, so the broad boundary is visible in the log rather than mistaken for a chosen one.

This repository is in that state. Its `.clew.yaml` declares only `guard:`, so `clew index` takes the whole-repo path.

**Caveat I did not verify.** The code says that without a git repository, `_gitignored_paths` returns nothing and logs a warning. The scope then falls back to the dot and cache exclusions alone. I read the code path but did not run it.