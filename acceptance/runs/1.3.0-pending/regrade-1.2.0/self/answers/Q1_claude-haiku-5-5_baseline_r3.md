**Short answer:** the repository's own `index_scope:` declaration decides, and it is the only tier that makes a real scope decision. With nothing declared, the scope is the whole repository minus what git ignores, plus dot and cache directories. The Doxyfile no longer decides scope (gh#333), and the gate's config doesn't either.

I read the code in `clew/scope.py`, `clew/treescan.py`, `clew/declaration.py`, `clew/doxygen.py`, `clew/harvest.py` and `clew/filetypes.py`. I did not run a build, so the behaviour below is from reading the code.

**Decision flow**

```
derive_scope(repo_root)
 ├─ load .clew.yaml (no file / no index_scope → None)
 ├─ index_scope present but unusable → _Rejected → refuse the build (CLI exits 1)
 ├─ index_scope with roots that exist → SOURCE_DECLARED (roots replace the scope)
 └─ otherwise → whole_repo_scope(repo)
        roots    = [repo]
        excludes = git-ignored paths
                 + nested-repo ignores
                 + dot-directories and __pycache__/node_modules
```

**Tier 1: a declaration.** `_declared_index_scope` (`scope.py` ~991) reads `index_scope:` from `.clew.yaml`. Only `roots` and `excludes` are accepted; any other key is rejected. `roots` is required, because `excludes` alone does nothing. Roots that don't exist on disk are dropped. A present-but-unusable section is refused at the CLI, not quietly widened to the whole repo.

**Tier 2: nothing declared.** `whole_repo_scope` (`scope.py` ~683) is the default. Its root is the repository itself, and nested git trees are included and tagged rather than cut out. Exclusions come from three places:

- **Git-ignored paths.** `git ls-files --others --ignored --exclude-standard --directory` (`_gitignored_paths`, ~845). Wholly ignored directories collapse into one entry. Each nested repo's own ignores are collected separately, because the parent's `ls-files` stops at the submodule boundary.
- **Dot and cache directories.** Any directory whose name starts with `.` is pruned at any depth, along with `__pycache__` and `node_modules`. This applies even when git does not ignore them, so `.github/` is excluded.
- **Depth cap.** Below depth 16 the walk stops pruning and takes the directories wholesale. The limit is recorded for provenance.

If the repo is not under git, a warning is logged and no git-ignored paths are excluded. Only the dot and cache pruning applies.

**What doxygen then reads.** The whole-repo root goes in as doxygen's INPUT, with the exclusions as EXCLUDE. `FILE_PATTERNS` is forced to doxygen's own broad default list (`DOXYGEN_DEFAULT_FILE_PATTERNS`, `doxygen.py` ~203), which includes `*.py`, `*.h`, `*.md`, `*.java` and many more. A repo's declared `FILE_PATTERNS` no longer vetoes files (gh#340). A repo's own Doxyfile still supplies ALIASES and PREDEFINED, but its INPUT is ignored.

**What filters after that.**

- `enumerate_tree` (`treescan.py` ~203) is deliberately not extension-filtered. Every file under INPUT is hashed for the cache, so the cache errs toward a miss.
- Binary files are dropped by `lang_parsing_substrate.classify_file` (`filetypes.py`), both from the scanned tree and before every harvest read.
- Symbol parsing is by extension. `harvest.py` maps suffixes to tree-sitter grammars (C, C++, Python, Rust, JS, TS, shell, CMake). A file whose extension matches no grammar is hashed but not parsed.

**Things worth knowing:**

- The decision is per build, and `derive_scope` resets the depth-limit record on each call.
- This repo's own `.clew.yaml` has only a `guard:` section, so `clew index` on it runs on the whole-repo default. Its comment says so explicitly.
- Because the default is wide, a repo with large vendored trees that are not gitignored will be indexed in full unless it declares `index_scope:` with `roots:` and `excludes:`.