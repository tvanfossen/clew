When clew indexes a repository, the file set comes from one decision in `clew/scope.py`, `derive_scope()`. It returns one of two scopes: the repo's own declared `index_scope:`, or the whole repository minus a set of subtractions. The Doxyfile is no longer a tier (gh#333).

**The decision**

```
derive_scope(repo_root)
 ├─ load_declaration_located(root)        reads <repo>/.clew.yaml only
 │    ├─ file absent / unreadable         → treated as absent (warning if malformed)
 │    └─ unknown top-level section        → DeclarationError (refused, not ignored)
 ├─ _declared_index_scope()
 │    ├─ no index_scope: key             → None → fall through
 │    ├─ present but unusable             → _Rejected(reason) → WARNING, whole repo
 │    │     (not a mapping, unknown key, no roots that survive)
 │    └─ usable                           → DerivedScope(SOURCE_DECLARED, roots, excludes)
 └─ whole_repo_scope(root)                → DerivedScope(SOURCE_WHOLE_REPO, roots=(root,), excludes=…)
```

**Declared scope.** `roots:` and `excludes:` are repo-relative. `_existing_paths()` resolves each entry, then checks it stays inside the repo, then checks it exists. Absolute and `../` entries are refused (security audit H5). Missing roots are dropped with a warning. Declared roots are taken at their word and never walked, so a vendored clone inside a declared root is indexed without being noticed. The reason string names the file it was read from.

**Nothing declared (the zero-config path).** This is `whole_repo_scope()`, which is the default tier. Its single root is the repository itself. Its excludes are:

1. **Git-ignored paths.** `_gitignored_paths()` runs `git ls-files --others --ignored --exclude-standard --directory` through `git_argv`/`git_env`, so a target's own `.git/config` cannot run commands. It also collects each nested submodule's own ignores, because the parent's `ls-files` stops at the submodule boundary.
2. **Dot-directories and caches.** `_pruned_dirs()` walks the tree and excludes any directory where `_skip_dir()` matches: names starting with `.`, plus `__pycache__` and `node_modules`. It stops at nested git trees and keeps only their top-level dot-directories. The walk has a depth limit of 16, and anything below it is recorded rather than silently dropped.

Nested git trees are not excluded. They are indexed, and `external.py` tags their rows so a question about the parent and a vendored library can still be told apart.

**Edge cases in the zero-config path**

- If the repo is not a git repository, `_gitignored_paths()` returns nothing and logs a warning. Only the dot/cache pruning then applies, so the index is wider than the repo's own `.gitignore` would suggest.
- The reason string always says why the whole-repo tier was chosen: either "no `index_scope:` is declared" or the specific rejection message.

**A stale comment to fix.** The docstring of `_declared_index_scope()` still says that returning `None` "drops the resolution to the Doxyfile's own INPUT". That contradicts `derive_scope()` and `whole_repo_scope()`, which both say the Doxyfile no longer supplies INPUT. The code is correct; the comment is not.

I did not re-verify `load_declaration_located()` against the file on disk. The index marked its line anchors as out of date, so I relied on its body text. Nothing in the repo was edited.