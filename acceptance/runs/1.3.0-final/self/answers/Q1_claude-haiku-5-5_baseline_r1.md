Nothing about the repository is read from the Doxyfile for scope anymore. What goes into the index is decided by two separate steps: which trees are walked (scope), then which file types each front end accepts. I read this from the source; I did not run a build.

**Step 1: scope (which trees are walked)**

`clew/scope.py:derive_scope` checks for a declared `index_scope:` section, in the repo's `.clew.yaml` or a `--declare` file, with `roots:` and `excludes:` keys.

- A declared `index_scope` is used only if it is usable. `roots:` is required, and `excludes:` alone is rejected. Unknown keys are rejected. Roots that do not exist on disk are dropped.
- A rejected declaration is refused at the CLI with exit 1 (`clew/cli.py`, around line 807). It is not silently widened.
- Declared roots replace the scope; they do not add to it. `clew/propose/notindexed.py` says so explicitly.

**What happens when nothing is declared**

The fallback is `whole_repo_scope` (`scope.py:683`):

- **Root:** the whole repository, including nested git trees.
- **Excludes, from git:** whatever `git ls-files --others --ignored --exclude-standard --directory` reports. That is run in the root and in each nested tree, so a submodule's own `.gitignore` applies.
- **Excludes, by name:** any directory whose name starts with `.`, plus `__pycache__` and `node_modules`.
- **Nested trees:** they are indexed, not excluded (gh#333). `external.py` tags their rows afterwards so their files can be told apart.
- **Depth:** the walk stops at depth 16. Anything deeper is taken wholesale and recorded.
- **Not a git repo:** nothing is ignored, and a warning is logged.
- **Log:** the reason string records which tier was used and why, so the build log says "no index_scope is declared … the whole repository is the index scope".

The scope is then applied by `_fold_scope_into_args` (`cli.py:739`). It sets the INPUT to the root, sets EXCLUDE to the excludes, and sets `replace_input`, so the target Doxyfile's INPUT is discarded.

**Step 2: file types (which files inside those trees are read)**

- **Doxygen (C/C++, Python, Java, and so on):** `FILE_PATTERNS` is forced to `DOXYGEN_DEFAULT_FILE_PATTERNS` (`doxygen.py:203`, gh#340). A target's own declaration cannot narrow it. Doxygen sees only files matching that list.
- **Parse-built front end (`clew/synth.py`):** it claims `.js/.mjs/.cjs/.jsx/.ts/.mts/.cts/.tsx`, `.sh/.bash/.cmake`, `CMakeLists.txt`, and `.yaml/.yml/.json`. The YAML and JSON files are registered but not harvested for symbols. Markdown is not claimed here, on purpose, because it is chunked for full-text search.

**Caveats I noticed**

- The hash-and-cache set is broader than the index. `enumerate_tree` is deliberately not extension-filtered, so every file under INPUT is hashed for cache invalidation, including files that are never indexed.
- `*.md` and `*.markdown` appear in Doxygen's default `FILE_PATTERNS`, so Doxygen reads Markdown even though the synth front end does not claim it. I did not trace how that output is used, so I cannot say whether Markdown ends up as searchable rows.
- This repo's own `.clew.yaml` declares no `index_scope`, so it gets the whole-repo tier. Its `guard: validate: exclude:` list (`tests/`, `acceptance/`, `scripts/`) is gate configuration and does not affect the index. The scope code does not read it. That means `acceptance/` and `tests/` are indexed unless git ignores them.