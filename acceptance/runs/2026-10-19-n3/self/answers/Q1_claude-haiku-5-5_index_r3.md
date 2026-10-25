The short answer: a repository's own `index_scope:` declaration is the only thing that narrows the index. Without one, clew indexes the whole repository minus what git ignores. The decision lives in `clew/scope.py`, and `_apply_scope` in `clew/cli.py` applies it to the build.

**The decision, in order**

1. **Declaration present and usable.** `derive_scope` calls `_declared_index_scope`, which reads `.clew.yaml` (via `load_declaration_located`) and looks for an `index_scope:` section. The section's `roots:` replace the index input and are required. Each root is taken at its word and never walked. `excludes:` are optional and only subtract from the roots. Declaring `excludes` alone does nothing, and a root that doesn't exist on disk is dropped.

2. **Declaration present but unusable.** Unknown keys, a non-mapping section, or no surviving roots produce a `_Rejected` result. `derive_scope` logs a warning and falls through to the whole-repo tier, with the rejection reason carried in the scope's `reason`. The `_apply_scope` comment at `clew/cli.py` says a rejected declaration is refused there rather than absorbed. I read that from the comment and did not trace the exact control flow.

3. **No declaration.** `whole_repo_scope` returns one root, the repository itself. Its excludes are:
   - every path `git ls-files --ignored --exclude-standard --directory` reports, run with a hardened `git_argv`/`git_env` so the target repo's own config can't execute code;
   - the same list for each nested git tree, since a submodule's `.gitignore` is invisible to the parent;
   - dot-directories and `__pycache__`/`node_modules` (`_pruned_dirs`, which stops descending at nested trees and at depth 16).

**What happens when nothing is declared**

- The index covers the whole tree less ignored paths, including nested git trees and submodules. `external.py` tags those rows afterwards so answers can still say which codebase a call belongs to.
- A repo's Doxyfile no longer decides scope. Its `INPUT` is replaced. Its `ALIASES` and `PREDEFINED` are still used.
- The `doxygen-guard` gate's `files:` pattern is deliberately ignored, because it answers what must be documented, not what should be indexed.
- If the directory isn't a git repository, `_gitignored_paths` logs a warning and excludes nothing, so the scope is wider than intended but still works.
- The build reports the reason in its log, naming where a declaration was looked for and how to declare one.

**Where the code disagrees with itself**

The module docstring says "TWO tiers", but in practice the whole-repo tier is the default and only fallback. The Doxyfile tier was removed in gh#333. The index also contains a test, `test_cli_apply_scope_indexes_the_whole_repo_without_a_declaration`, that pins the undeclared behaviour to the whole repo under `from-guard`.

Index status for this repo is current (`stale: false`). I could not look up `clew/scope.py` itself through `dossier`, which returned no entry for the file path, so the file contents above come from reading source directly.