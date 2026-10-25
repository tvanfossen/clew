Nothing is decided by a Doxyfile anymore. Two things decide what gets indexed: a scope tier (which trees are walked) and doxygen's `FILE_PATTERNS` (which extensions are read). The scope tier is set by the repo's own declaration if it has one, and by the repository itself if it doesn't. I read the code but did not run a build, so the behaviour below is from source, not measured output.

```
.clew.yaml index_scope?  ──yes──> roots (repo-relative, must exist) minus excludes
        │ no
        ▼
whole repo ─ minus git-ignored paths (per tree, incl. nested git trees)
           ─ minus dot-dirs, __pycache__, node_modules
        │
        ▼
enumerate_tree (no extension filter; prunes excluded subtrees)
        │
        ▼
_drop_binary_files (lang_parsing_substrate classifies; binaries → extra_exclude)
        │
        ▼
doxygen: INPUT = scope roots, FILE_PATTERNS forced to the default list
        │
        ▼
index (JS/TS contribute through the parse front end, not doxygen)
```

**1. Declared scope (tier 1).** `clew/scope.py` `_declared_index_scope` reads `index_scope:` from the repo's `.clew.yaml`. It takes `roots` and `excludes`, both repo-relative. Roots that don't exist are dropped with a warning. `roots` is required, so `excludes` alone does nothing. Unknown keys reject the whole section rather than being ignored. A rejected section falls back to whole-repo, and the log says why.

**2. Nothing declared (tier 2, the default).** `whole_repo_scope` in the same file makes the repository root the single INPUT root. Excludes come from:
- `git ls-files --others --ignored --exclude-standard --directory`, which is the `.gitignore` set, run for the parent repo and for each nested git tree.
- Dot-directories (`.git`, `.venv`, and so on), plus `__pycache__` and `node_modules`, via `_pruned_dirs`.

Nested git trees (submodules, vendored clones) are indexed, not cut out. `external.py` tags their rows afterwards. If the directory isn't a git repo, the ignore list is empty and a warning is logged, so the scope is wider than the repo asked for. That is the failure mode the code comments say the project keeps guarding against.

**3. Enumeration.** `treescan.enumerate_tree` walks the roots and prunes excluded subtrees during the walk. It deliberately does not filter by extension. Every file under scope is hashed for cache invalidation, so an edit to a non-source file still forces a doxygen re-run. That hashing is for cache keys only; it does not put files in the index.

**4. Binary removal.** `cli._drop_binary_files` classifies each file by content, not extension, and drops binaries. It adds them to `extra_exclude` and logs each skip at INFO. Text files of any size stay.

**5. Doxygen's file-type filter.** `doxygen.py` forces `FILE_PATTERNS` to `DOXYGEN_DEFAULT_FILE_PATTERNS` (C/C++, Java, Python, Fortran, Markdown, VHDL, and so on) and replaces `INPUT` with the resolved scope (`RECURSIVE=YES`). A repo's declared `FILE_PATTERNS` is read only for reporting; it cannot veto a file that scope admitted (gh#340). The repo's Doxyfile still supplies ALIASES and PREDEFINED.

**What happens when nothing is declared:** the whole repository is indexed, less what git ignores, less dot and cache directories, less binaries. Doxygen then keeps only files with the default extensions, and JS/TS files are picked up through the parse front end. `derive_scope` puts an explanation in the build log saying no `index_scope` was declared and naming where one would go.

**Caveats I did not verify by running:**
- `git ls-files --others --ignored` lists only untracked ignored entries. A file that is tracked and also matches a `.gitignore` pattern should stay in scope. I inferred this from git's semantics.
- The `index_scope` / `excludes` semantics above are from the docstrings and code, not from a test run. The relevant tests are `tests/test_scope.py`, `tests/test_treescan_pruning.py` and `tests/test_binary_*` if you want to confirm them.