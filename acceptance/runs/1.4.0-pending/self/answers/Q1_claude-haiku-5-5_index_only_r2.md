**Short answer:** the index scope is decided once per build, from the repo's `.clew.yaml` `index_scope:` section. If that section is absent, the whole repository becomes the scope, minus git-ignored paths and dot/cache directories. A Doxyfile no longer decides anything about which files are indexed.

**How the decision is made**

1. **Entry point.** `_apply_scope` in `clew/cli.py` runs for the default `--scope from-guard`. It asks `declared_scope_rejection` whether a stated scope would be refused. A rejected declaration stops the build with exit 1 and an error. It is not silently widened. (`derive_scope` itself does fall back to the whole repo, but only for internal callers that must always get a usable scope.)
2. **Declared path.** `_declared_index_scope` in `clew/scope.py` reads `index_scope:` from `.clew.yaml` (via `load_declaration_located`). The accepted keys are `roots` and `excludes`, and anything else is refused by name. `roots` is required; `excludes` alone is rejected. A root that does not exist on disk is dropped. Declared roots are taken at their word and never walked. Nested git trees under a root are indexed and tagged afterwards by `external.py`, so two codebases in one index can still be told apart.
3. **Undeclared path.** `derive_scope` falls through to `whole_repo_scope`. That tier sets one root, the repository itself, and computes excludes from two sources:
   - Git-ignored paths, from `git ls-files --others --ignored --exclude-standard --directory`, run per repository including nested trees. It goes through `git_argv` and `git_env` so a target's own `.git/config` cannot execute anything.
   - Dot and cache directories, from `_pruned_dirs`. The walk stops at nested git trees but keeps their top-level dot directories. There is also a depth limit (`_MAX_DEPTH`), and hitting it is recorded in `_DEPTH_LIMITED`.
4. **Fold into the build.** `_fold_scope_into_args` writes the roots into the INPUT list and the excludes into the EXCLUDE list, with `replace_input=True`. Doxygen therefore no longer takes INPUT from the Doxyfile. The Doxyfile still supplies ALIASES and PREDEFINED only.
5. **Logging.** `derive_scope_logged` logs a declared scope at INFO. A whole-repo default is logged at WARNING with the reason, so nobody mistakes a boundary nobody chose for one somebody did.

**What happens with nothing declared (this repository's state)**

The index reports that `.clew.yaml` exists but carries no `index_scope`. So the source is `whole-repo`, the root is `.`, and excludes are `.git, .claude-plugin, .github` plus the git-ignored paths. The build reports 435 files in scope. It also records 14 in-scope files that hold no rows, grouped by type: no extension ×3, `.csv` ×3, `.rs` ×2, `.toml` ×2, and one each of `.jsonl`, `.lock`, `.motor`, `.sql`. That `not_indexed` report is measured on the build's own walk, so an empty query answer can be read as "this file type was not indexed" rather than "the symbol does not exist".

**Gaps in what I could verify from the index**

- I did not read the body of `_skip_dir`, so the exact dot/cache rule is described only from its docstring.
- I did not establish from the index which file extensions the parser accepts. The `not_indexed` report shows the gap but not the accepted list.
- `load_declaration_located` reported an anchor mismatch (its lines moved since the build), so its line numbers may be stale. Its behaviour, as described in its docstring, was consistent with the above.