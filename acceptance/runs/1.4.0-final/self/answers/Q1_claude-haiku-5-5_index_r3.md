**Short answer:** the file set is decided by the repo's own `index_scope:` declaration in `.clew.yaml`, and if there isn't one, by the whole repository minus what git ignores. A Doxyfile's `INPUT` no longer plays any part in it.

```
clew build --scope from-guard (the default)
        │
        ▼
cli._apply_scope                              clew/cli.py:758
        │
        ├─ --scope is not from-guard?  → refuse if index_scope was stated, else return
        │
        ├─ declared_scope_rejection()          clew/scope.py:612
        │     index_scope present but unusable (e.g. excludes-only, no roots)?
        │         → log error, sys.exit(1)   (no silent fallback)
        │
        ▼
scope.derive_scope()                           clew/scope.py:639
        │
        ├─ _declared_index_scope()             clew/scope.py:991
        │     reads .clew.yaml index_scope: roots / excludes
        │     roots taken as written (repo-relative); missing roots dropped with a warning
        │     returns a DerivedScope, or None if no index_scope key
        │
        └─ None → whole_repo_scope()           clew/scope.py:683
              roots = (repo root,)
              excludes = git-ignored paths
                       + dot-dirs and __pycache__/node_modules
                       + nested git trees' own ignores
        │
        ▼
_fold_scope_into_args → args.extra_input = roots, args.extra_exclude = excludes,
                        replace_input = True                 clew/cli.py:739
```

**How the decision is made, in order:**

1. **Declaration first.** `_declared_index_scope` reads `index_scope:` from `.clew.yaml`. It accepts only `roots:` and `excludes:`, and rejects unknown keys. Roots are repo-relative and taken at face value, so the tool never walks them to check. A declaration with `excludes:` but no `roots:` is refused outright at build time, because the old behaviour of quietly widening to the whole repo caused a 900s doxygen timeout (per the comments on `declared_scope_rejection`).

2. **Whole repo when nothing is declared.** `whole_repo_scope` is the default tier since gh#333. It indexes the entire tree, including nested git repos and submodules. The subtractions are only what the repo already says about itself:
   - Paths matched by `git ls-files --ignored --exclude-standard`, run through `gitenv.git_argv` so a cloned repo's config can't execute code.
   - Each nested repo's own ignores, which git otherwise hides at the submodule boundary.
   - Dot-directories and `__pycache__`/`node_modules`, pruned by `_skip_dir`, down to a depth of 16 (`_MAX_DEPTH`).

3. **The Doxyfile is not a tier.** Its `INPUT` used to be the fallback. That inverted the tool: a repo that shipped a Doxyfile got only its published-API headers, and a repo without one got everything. The Doxyfile still supplies `ALIASES` and `PREDEFINED`, but its `INPUT` is replaced. The doxygen-guard `files:` pattern is also not a scope input; it governs what must be documented, not what gets indexed.

4. **Nested trees are indexed and tagged, not excluded.** `external.py` tags their rows after the build, so an answer can still say which codebase a symbol came from.

**What this repo does:** its `.clew.yaml` has only a `guard:` section and no `index_scope:`. So a bare build takes the whole-repo path. Git-ignored paths are excluded, nested trees are included, and dot/cache directories are pruned. `AGENTS.md` says the same thing: this repo "declares nothing here and builds on its defaults."

**Two details worth knowing:**
- `--scope from-guard` is the default and is the only value that reads the declaration. `from-declaration` is an alias for it, per `tests/test_scope_alias.py`. Stating an `index_scope` with any other `--scope` is refused, not silently ignored.
- `derive_scope` itself never refuses. It absorbs a rejected declaration into the whole-repo tier. Only the CLI and the MCP refresh path check `declared_scope_rejection` first and stop. Internal callers can therefore end up with a wider scope than the declaration asked for, unless they run that check themselves.