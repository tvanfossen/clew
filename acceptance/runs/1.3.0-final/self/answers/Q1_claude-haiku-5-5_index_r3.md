**Short answer:** the index scope is decided by a single function, `derive_scope`. A repo's own `index_scope:` declaration wins if it has one. Otherwise the scope is the whole repository, minus what git ignores and minus dot and cache directories. Nothing is guessed, and a Doxyfile does not decide the file set.

```
derive_scope(repo_root, stated?)                 clew/scope.py:639
  │
  ├─ _declared_index_scope()                     clew/scope.py:991
  │    ├─ stated by caller (tier 1)?  → use it
  │    ├─ else load .clew.yaml → index_scope: section?
  │    │     absent                 → None → fall through
  │    │     present but unusable   → _Rejected → whole-repo, with the reason recorded
  │    │     usable                 → DerivedScope(SOURCE_DECLARED, roots, excludes)
  │
  └─ whole_repo_scope(root)                      clew/scope.py:683
         roots    = (repo_root,)
         excludes = git-ignored paths   (both sides of every nested git tree)
                  + dot dirs and __pycache__/node_modules (_pruned_dirs, _skip_dir)
```

**The declared tier.** `index_scope:` takes `roots:` and `excludes:` only. Any other key is refused by name, not silently ignored. Roots are repo-relative. A root that does not exist is dropped. If no usable root survives, the declaration is rejected and the build falls back to the whole repo, with the rejection reason written into the log. Declared roots are taken at their word and never walked.

**The whole-repo tier (what happens when nothing is declared).**
- The root is the repository itself. Nested git trees are included, not cut out (gh#333). `external.py` tags their rows afterwards so two codebases stay distinguishable in answers.
- Excludes come from `git ls-files --ignored --exclude-standard --directory`, run through `git_argv`/`git_env` so a target's own `.git/config` cannot execute code. Each nested repo's own ignores are collected separately, because git does not report them through the parent.
- `_pruned_dirs` adds dot-directories and `__pycache__`/`node_modules` anywhere in the tree. The walk stops at nested-tree boundaries and at depth 16, and it records where it stopped.
- The reason string says "no `index_scope` is declared", names the file it looked in, and says the Doxyfile supplies aliases and predefines but not INPUT.

**Downstream.** The doxygen stage uses the same roots and excludes via `enumerate_tree` (`clew/treescan.py:203`), which is deliberately not extension-filtered. A build with no doxygen stage (Rust or JS/TS only) reaches the same answer through `_scanned_files` (`clew/cli.py:2483`). That path reuses the derived scope, and falls back to `[repo_root]` when nothing is declared.

**This repository.** `.clew.yaml` at the root has only a `guard:` section and no `index_scope:`. Its header says the index "builds this repo on its defaults". So the self-index is the whole tree, less `.gitignore` and dot/cache directories. That includes `acceptance/`, `tests/`, and `clew/`, since nothing excludes them.

**Limits of what I checked.** I read `derive_scope`, `whole_repo_scope`, `_declared_index_scope`, `_gitignored_paths`, `_pruned_dirs`, `_skip_dir`, `_scanned_files` and `enumerate_tree`. The `_scanned_files` docstring also mentions "operator" and "toolchain" exclusions (`toolchain.toml`, a skip count). I did not trace those, so I can't confirm how they apply.