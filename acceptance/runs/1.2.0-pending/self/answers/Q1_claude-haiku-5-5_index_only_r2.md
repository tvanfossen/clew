**Short answer:** the index scope is decided in one place, `derive_scope` in `clew/scope.py`. A repo's own `index_scope:` declaration wins if it is usable. If nothing is declared, the whole repository is the scope, minus what git ignores and a few cache and dot directories.

**How the decision is made**

1. **Declared scope (tier 1).** `derive_scope` calls `_declared_index_scope`, which reads the `index_scope:` section from the repo's declaration file (`.clew.yaml`) via `load_declaration_located` in `clew/declaration.py`. A caller can also state a scope directly, and it goes through the same construction.
   - `roots:` is required. `excludes:` alone does nothing.
   - Roots that don't exist on disk are dropped.
   - Unknown keys in the section, or a section that isn't a mapping, reject the declaration.
   - A usable declaration becomes a `SOURCE_DECLARED` scope whose roots are taken as written and never walked.

2. **Whole repository (tier 2).** If no declaration exists, or it is rejected, `whole_repo_scope` runs:
   - One root: the repository itself.
   - Excludes come from `git ls-files --ignored --others --exclude-standard --directory`, run through `git_argv`/`git_env` so a target's own git config cannot execute code. This runs once for the top repo and again for each nested git tree, because a submodule's `.gitignore` is invisible to its parent.
   - Dot-directories and `__pycache__` and `node_modules` are pruned anywhere in the tree (`_skip_dir`, `_pruned_dirs`). They are added as exclude entries because the whole-repo root is never walked for files.
   - Nested git trees are included, not cut out (gh#333). `external.py` tags their rows afterward so two codebases in one index can still be told apart.
   - Walking stops at depth 16. Deeper directories are taken wholesale and recorded in `_DEPTH_LIMITED`, and a warning is logged.
   - If the directory is not a git repository, nothing is excluded for ignores and a warning says so. The scope is wider than the repo asked for.

**What the Doxyfile does now.** It no longer decides scope. Its `INPUT` is ignored (gh#333), because treating a documentation target as a reasoning boundary made repos that shipped a Doxyfile get narrower indexes than repos that didn't. Its `ALIASES` and `PREDEFINED` are still used. The doxygen-guard gate's `files:` pattern is also not a scope tier.

**What happens when nothing is declared.** You get tier 2. The reason string is set to say that no `index_scope` was declared, where the declaration was looked for, and what was excluded. That reason is what the build logs and what `IndexScope` reports, so the scope is never silently guessed.

**Things I could not settle from the index**

- A rejected declaration: `derive_scope` logs a warning and falls back to whole-repo scope. But `tests/test_scope.py` has a test named `test_cli_apply_scope_refuses_a_rejected_declaration`, which says the CLI build refuses instead of widening. Both can be true, since the CLI and the library call may differ, but I could not read `cli.py` to confirm.
- `toolchain.toml` `[ignore].paths` and `suppress.toml` entries with `tool = "*"` are documented as index-side exclusions, but I did not confirm they feed into `whole_repo_scope`.
- `load_declaration_located` came back with `anchor_mismatch: true`, so its line numbers and possibly its text predate the current file. Treat its description as approximate.