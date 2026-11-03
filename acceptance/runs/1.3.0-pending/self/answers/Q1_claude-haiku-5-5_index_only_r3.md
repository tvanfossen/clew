**Short answer:** the file set is decided by the index scope, which is resolved once per build into a list of roots plus excludes. If the repo declares an `index_scope:` with usable `roots:`, that declaration is the decision. If it declares nothing, the whole repository is the scope, minus what git ignores and minus dot and cache directories.

**Resolution order** (`clew/scope.py`, `derive_scope` at line 639)

```
derive_scope(repo_root, stated?)
 ├─ _declared_index_scope(...)            index_scope: in .clew.yaml (or a caller-stated scope)
 │    ├─ section absent                 → None → fall through
 │    ├─ present but not a mapping      → rejected
 │    ├─ unknown key (only roots/excludes allowed) → rejected
 │    ├─ no existing root               → rejected
 │    └─ usable                         → DerivedScope(source=declared, roots, excludes)
 └─ whole_repo_scope(root)              the default tier
```

A rejection is logged as a warning. `derive_scope` then falls back to the whole repository, but the CLI does not accept that. `_apply_scope` (`clew/cli.py:758`) calls `declared_scope_rejection` first and exits with an error, so a broken declaration fails the build rather than silently widening it.

**What the declaration says**

- `roots:` is required and is repo-relative. Roots that don't exist on disk are dropped. A declared root is taken at its word and never walked.
- `excludes:` alone does nothing. Excludes outside the repo are dropped.
- The only keys accepted are `roots` and `excludes`.

**What happens when nothing is declared**

`whole_repo_scope` (`clew/scope.py:683`) returns one root, the repository itself, and excludes two things:

1. Everything `git ls-files --others --ignored --exclude-standard` reports for the top-level tree and for each nested git tree. `_gitignored_paths` runs git through `git_argv`/`git_env`, so a target's own `.git/config` cannot run commands.
2. Dot-directories and `__pycache__`/`node_modules` (`_skip_dir`, `_SKIP_DIR_NAMES`), pruned by `_pruned_dirs`.

Nested git trees are included, not excluded. `external.py` tags their rows afterwards so codebases can still be told apart in answers. The doxygen-guard `files:` pattern is not read; it answers what must be documented, not what should be indexed.

**The Doxyfile is no longer a tier** (gh#333). A Doxyfile's `INPUT` is a documentation target, not a reasoning boundary. Repos with a Doxyfile used to get the narrower published-API subset, and repos without one got everything. Now both get the whole repository. The Doxyfile still supplies ALIASES and PREDEFINED.

**Build path:** `_apply_scope` folds the chosen scope's roots and excludes into the build arguments (`_fold_scope_into_args`), with `replace_input` set. `--extra-input` and `--extra-exclude` are appended on top. The one escape hatch is `--scope doxyfile`, an explicit operator opt-out that folds nothing. Scope provenance (source, reason, roots, excludes, and the in-scope file count) is stamped into the build metadata, repo-relative only.

**Caveat:** `_declared_index_scope`'s docstring still says a missing declaration "drops to the Doxyfile's own INPUT". The code in `derive_scope` and `whole_repo_scope` says otherwise, and gh#333 is the change that removed that path. I read this from the index's docstrings and bodies, not by running it, so the code is the authority if they disagree.