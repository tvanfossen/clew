**Short answer:** the index's file set is decided by a declared `index_scope:` in the repo's `.clew.yaml`, or, when nothing is declared, by the whole repository minus what git ignores. Extension filtering is not clew's decision. Doxygen's default `FILE_PATTERNS` applies it during the doxygen run. I read the source but did not run `clew index` against this repo, so the behaviour below is from the code, not an observed build.

## Decision flow

```
build starts
  │
  ├─ CLI --scope / explicit flag ─────────────► wins over the file (declaration.py)
  │
  ├─ .clew.yaml has index_scope:?
  │     ├─ valid roots (exist on disk) ───────► roots taken at their word, never walked
  │     │                                        excludes applied; scope.py _declared_index_scope
  │     └─ section present but unusable ──────► logged as rejected, falls through
  │          (excludes-only, unknown key,
  │           no existing roots, not a mapping)
  │
  └─ nothing usable ──────────────────────────► whole_repo_scope(root)   (scope.py)
        root = repo root
        excludes = git-ignored paths
                 + nested-tree ignores (submodules / vendored clones)
                 + dot-dirs and __pycache__ / node_modules
        nested git trees INCLUDED, not cut out
        │
        ▼
  doxygen run (doxygen.py forces the Doxyfile's flags)
        INPUT         replaced by the scope roots
        EXCLUDE       cleared; scope excludes passed as EXCLUDE entries
        FILE_PATTERNS replaced by doxygen's own default extension list
        RECURSIVE     = YES
        │
        ▼
  per-file binary check (treescan.binary_files, via lang_parsing_substrate)
        binary files skipped and logged at INFO; empty and large text files kept
```

## What "nothing declared" means

1. **Scope tier.** `derive_scope` falls through to `whole_repo_scope`, and the reason string records why (for example "no index_scope is declared for this repo"). Since gh#333 this is the default, not a last resort. A repo's Doxyfile `INPUT` no longer decides scope. The Doxyfile is still read for `ALIASES` and `PREDEFINED`, but its `INPUT` and `FILE_PATTERNS` are replaced.

2. **Exclusions.** Only what the repo already says about itself, plus housekeeping:
   - Git-ignored paths, from `git ls-files --ignored --others --exclude-standard --directory`, run with the sanitised `git_env()`. Submodules and nested clones contribute their own `.gitignore` entries.
   - Dot-directories and `__pycache__` / `node_modules` at any depth (`_skip_dir`).
   - Walk-depth guard at 16 levels, which is a runaway guard rather than a policy.
   - If git is missing or the tree is not a repo, nothing is excluded and a warning is logged. The index is wider than intended and says so.

3. **Extension filtering happens in doxygen, not in clew's walk.** `enumerate_tree` is deliberately not extension-filtered, so every file under the roots is hashed for cache identity. Doxygen then applies `DOXYGEN_DEFAULT_FILE_PATTERNS`, a broad list of C/C++, Python, Java, Fortran, Markdown and similar extensions, which is what `doxygen -g` writes. A repo's own `FILE_PATTERNS` is not honoured (gh#340), so a declaration cannot veto a tree that scope admitted.

4. **Binary detection** runs before parsing. Non-text files are skipped, but there is no size limit, so a large generated `.c` is still read.

## Declared scope, for contrast

- `roots:` is required. `excludes:` alone is rejected, and the rejection is logged rather than silently absorbed.
- Roots that do not exist are dropped with a warning.
- A declared root is trusted and never walked, so a foreign clone inside it is indexed without notice. `external.py` tags those rows afterwards.

## This repo

`/home/tvanfossen/Projects/clew/acceptance/runs/1.3.0-pending/self/repo/.clew.yaml` declares only a `guard:` section, with `impact.requirements` and `validate` settings. It has no `index_scope:`, so this repo is indexed on the whole-repo default: everything not git-ignored, with `tests/`, `scripts/` and `acceptance/` included in the index even though they are excluded from the gate's `validate` list. That gate exclusion does not affect indexing.