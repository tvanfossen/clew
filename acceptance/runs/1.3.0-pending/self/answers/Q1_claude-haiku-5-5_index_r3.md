**Short answer:** the index's file set is decided by one function, `derive_scope` in `clew/scope.py`. It returns a single "scope" with roots and excludes. A repo's own `index_scope:` declaration wins if it is usable; otherwise the whole repository is the scope, minus what git ignores and minus dot and cache directories. The Doxyfile does not decide scope any more.

**Decision flow**

```
derive_scope(repo_root, stated?)                       clew/scope.py:639
  ├─ _declared_index_scope(root, stated?)              clew/scope.py:991
  │    ├─ no .clew.yaml index_scope section ──────────► None → fall through
  │    ├─ section present but not a mapping ──┐
  │    ├─ unknown key inside it (e.g. exclude:) ──┤  _Rejected: logged as a
  │    └─ no `roots:` that exists on disk ─────────┘  WARNING, then fall through
  │    └─ usable ──► DerivedScope(source=declared, roots, excludes)   [tier 1]
  └─ whole_repo_scope(root, rejected?)                clew/scope.py:683   [tier 2]
       roots    = (repo root,)
       excludes = git-ignored paths (both sides of every submodule boundary)
                + dot-dirs and __pycache__/node_modules  (_pruned_dirs, :908)
```

**Declared tier.** Only `index_scope:` in `.clew.yaml` is a decision about the index. Its keys are `roots` and `excludes`, both repo-relative. A root that does not exist is dropped with a warning. `roots` is required, because `excludes` alone does nothing. A declared root is taken at its word and never walked, so a foreign clone under it is indexed. The gate's `files:` pattern and the Doxyfile's `INPUT` are deliberately not tiers. `clew/scope.py`'s own docstring explains why. Honouring a Doxyfile `INPUT` once indexed 1,571 header declarations and zero of 108 `.c` implementations on Mbed-TLS. The repo's Doxyfile is still read for `ALIASES` and `PREDEFINED`, but its `INPUT` is replaced.

**Whole-repo tier (nothing declared).** This is the default, and the docstring says it is the default, not a last resort. Its subtractions come from three places:

- **Git-ignored paths.** `_gitignored_paths` runs `git ls-files --others --ignored --exclude-standard --directory`. It runs through `gitenv.git_argv` and `git_env()`, so a target's own `.git/config` cannot execute commands. The same list is collected inside each nested git tree, because `git ls-files` stops at a submodule boundary.
- **Nested git trees are indexed, not cut.** The walk stops at a nested tree's boundary but keeps its top-level dot-directories. `external.py` tags those rows afterwards so two codebases in one index can be told apart.
- **Dot and cache directories.** `_skip_dir` drops every name starting with `.`, plus `__pycache__` and `node_modules`. The walk stops at depth 16 and records where it stopped.

**Which files are then harvested.** Scope only decides which files are walked. Extension filtering happens later, and the two can differ. This repo's index reports 426 files, with `.c .cpp .h .json .md .py .yaml` held and `.rs`, `.toml`, `.csv` and others in scope but unindexed. `_not_indexed_scope` (`clew/cli.py:2646`) records that gap. It is what separates "the symbol does not exist" from "this file type was not indexed". Empty means nothing was missed, and the report is omitted when nothing walked the tree at all.

**This repo.** Its `.clew.yaml` declares only a `guard:` section and says "the index declares nothing here". So `derive_scope` returns the whole-repo tier with the reason "no index_scope is declared". The `scope` block in query replies shows the same result.

**Limits of this answer.** I read the scope and file-enumeration functions through the index. I did not read the code that passes roots and excludes into doxygen's `INPUT`/`EXCLUDE`, or the extension table that decides which harvesters run. Those are the places to check if you need the exact handoff.