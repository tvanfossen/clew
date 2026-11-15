**Short answer:** the index scope is decided by `derive_scope` in `clew/scope.py`. If the repo declares an `index_scope:` in its `.clew.yaml`, that declaration sets the roots. If nothing is declared, the whole repository is the root, minus what git ignores and a fixed set of dot and cache directories. Doxygen then filters by a forced extension list, not by anything the repo declares.

**Decision flow**

```
cli.py build  ──► derive_scope_logged(repo_root, stated?)
                        │
          ┌─────────────┴──────────────┐
  .clew.yaml index_scope:?          (absent)
   roots (required) + excludes         │
   usable? ── no ─► CLI: exit 1         │
        │ yes                          │
        ▼                              ▼
  DECLARED scope              WHOLE-REPO scope
  roots = declared dirs       roots = repo root
  excludes = declared         excludes = git-ignored paths
                                + dot dirs, __pycache__, node_modules
        └──────────────┬──────────────┘
                       ▼
          enumerate_tree(roots, excludes)   (walk, prune excludes)
                       ▼
          _drop_binary_files                (classify first 8 KiB)
                       ▼
          doxygen reads FILE_PATTERNS-matching files only
          + JS/TS via parse-built front end
```

**Tier 1: declared.** The `index_scope:` section in `.clew.yaml` accepts only `roots` and `excludes`, both repo-relative (`scope.py`, `_declared_index_scope`, `_existing_paths`). Several rules apply:
- `roots` is required. `excludes` alone is rejected, because it does nothing on its own.
- Absolute paths and `../` entries are refused, and paths that don't exist are dropped with a warning.
- A bad declaration does not fall back silently in the CLI. `cli.py` (around line 807) calls `declared_scope_rejection` and exits 1, because a silent fall-back would give the widest scope for the narrowest request.

**Tier 2: whole-repo (the default).** This is what a repo gets by saying nothing, whether or not it ships a Doxyfile (the Doxyfile INPUT tier was removed in gh#333). Its exclusions are:
- Everything `git ls-files --ignored --exclude-standard --directory` reports, run through `git_argv` and `git_env` so a cloned repo's config can't execute code. This runs once for the top repo and once for each nested git tree, so a submodule's own `.gitignore` applies.
- Dot directories (including `.git`, `.venv`) and `__pycache__`/`node_modules`, found by `_pruned_dirs`.
- Nested git trees are not excluded. They are indexed and tagged as external in `external.py`.
- If the directory isn't a git repo, or git is missing, nothing is ignored and a warning says so. The scope is then wider than the repo asked for.
- Walks go deeper than 16 levels are taken whole and logged rather than scanned.

**Enumeration and filtering.** `enumerate_tree` walks the roots and prunes excluded subtrees during the walk. It is deliberately not filtered by extension, because the incremental cache hashes every file under the roots and any change should invalidate. The one content filter is `_drop_binary_files` (`filetypes.py`), which removes files that look binary from the first 8 KiB. Those paths are added to the exclude list so doxygen never opens them. There is no size limit.

**What doxygen reads.** The build forces `FILE_PATTERNS` to doxygen's default list (`DOXYGEN_DEFAULT_FILE_PATTERNS`, since gh#340). A repo's own `FILE_PATTERNS` only produces a report, not a filter. The repo's Doxyfile still supplies `ALIASES` and `PREDEFINED`, but its `INPUT` and `EXCLUDE` are replaced by the scope. Markdown is handled separately by `prose.py`, which reads a curated list (README, `docs/*.md`, and so on) rather than `**/*.md`.

**This repo.** The clew repo's own `.clew.yaml` declares only a `guard:` section, with no `index_scope:`. Its comment says the index "builds this repo on its defaults," so it gets the whole-repo tier.

I worked from reading the code and did not run an index build, so the exact counts for this tree are unverified.