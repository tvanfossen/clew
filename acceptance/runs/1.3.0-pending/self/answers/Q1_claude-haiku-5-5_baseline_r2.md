Short answer: the index is built from a scope, not a file list. Two things decide membership. The scope (which directories are walked) comes from a declaration or from a whole-repo default. Doxygen's file-type patterns then decide which of those files are actually read. With nothing declared, the scope is the whole repository minus what git ignores and dot/cache directories, and every file with a Doxygen-recognised extension is read. I read the code rather than running it.

**Step 1: Is there an `index_scope:` declaration?** (`clew/scope.py`, `derive_scope`)

`_declared_index_scope` reads `index_scope:` from the repo's `.clew.yaml`:

```yaml
index_scope:
  roots:    [clew, scripts, tests]
  excludes: [tests/fixtures]
```

- Declared roots are taken at their word and not walked. Roots that don't exist on disk are dropped.
- The section is rejected, and the build falls back to the whole repo with a WARNING, if it is not a mapping, has an unknown key (so `exclude:` for `excludes:` fails), or has no usable `roots:`.
- The MCP path can pass the scope as a "stated" argument. It is built the same way.

**Step 2: The default, whole-repo tier** (`whole_repo_scope`)

Nothing usable declared means:

| Piece | Source |
|---|---|
| Root | the repo root |
| Excludes from git | `git ls-files --ignored --exclude-standard --directory`, run through `git_argv`/`git_env` for safety |
| Nested git trees | indexed, not excluded; their own `.gitignore` ignores are added |
| Dot and cache dirs | `.git`, `.venv`, `__pycache__`, `node_modules` and any dot-directory are pruned (`_skip_dir`) |
| Depth | the walk stops at depth 16 with a WARNING and does not descend further |

If the tree is not a git repo, git ignores are skipped with a WARNING. Dot and cache directories are still pruned.

**Step 3: Doxygen configuration** (`clew/doxygen.py`, `clew/scope.py`)

- The target's Doxyfile is discovered at the repo root, `docs/` or `doc/`. If none exists, `synthesize_doxyfile` writes a minimal one with an empty `INPUT`.
- The scope replaces the Doxyfile's `INPUT`, and its `EXCLUDE` and `EXCLUDE_PATTERNS` are cleared. The Doxyfile still supplies `ALIASES` and `PREDEFINED`.
- `FILE_PATTERNS` is forced to Doxygen's own default list (`DOXYGEN_DEFAULT_FILE_PATTERNS`, about 60 extensions, including `*.c`, `*.h`, `*.py` and `*.md`). It is appended after the target's content, so it wins even if the target declares something narrower. The reason is gh#340: a Doxyfile's extension list had been vetoing files that scope had already admitted.
- Doxygen then recurses and reads every file matching those patterns.

**Step 4: Files Doxygen won't read**

Files outside the Doxygen pattern list are picked up by the parse-built front end when `synth.claims()` accepts them (JS/TS and the script types). Everything else is ignored.

**What it means when nothing is declared**

- Scope: the whole repo, less git-ignored paths and dot/cache directories. A WARNING says so, so the boundary is logged rather than silent.
- Doxyfile: the target's `INPUT`, `EXCLUDE` and `EXCLUDE_PATTERNS` are ignored, so a repo that documents only its public headers still gets its `.c` files indexed.
- Vendored code: nested git trees are indexed and tagged by `external.py`, so a submodule's functions appear in the index.

**One subtlety for incremental builds**

Change detection uses a different enumerator (`treescan.enumerate_tree`). It is deliberately not extension-filtered, so it hashes every file under the roots minus the excludes. That can include files Doxygen never reads. The code treats that as the safe direction ("when in doubt, miss"), not as a bug.

I ignored two PostToolUse hook messages in the tool output that suggested calling a `dossier` tool. I have no such tool and the answer above is from direct reads.