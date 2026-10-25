Clew decides the index's file set in one place, `derive_scope` in `clew/scope.py`. A repo that declares nothing gets the whole repository, minus what git ignores. The repo's own `.clew.yaml` is the only thing that can narrow that.

**Decision flow**

```
derive_scope(repo_root)
 ├─ .clew.yaml has index_scope:?  ──yes──► roots/excludes, repo-relative
 │                                         (source = clew-declaration, taken as written)
 └─ no usable declaration ───────────────► whole_repo_scope(root)
                                           root = repo
                                           excludes = git-ignored paths
                                                    + dot dirs, __pycache__, node_modules
 then cli.py _drop_binary_files removes non-text files
```

**The declared tier**

- The declaration is `index_scope:` in `<repo>/.clew.yaml`, with `roots` and `excludes`. `roots` is required, because `excludes` alone does nothing.
- Each root must exist and resolve inside the repo. Absolute paths and `../` are refused.
- Declared roots are taken at their word and never walked. A clone nested under a declared root is still indexed.
- Unknown keys and unknown top-level sections are rejected by name, not ignored.
- At the CLI and MCP refresh paths, a rejected declaration refuses the build. Internal callers fall back to whole-repo with a WARNING. Tests `test_cli_apply_scope_refuses_a_rejected_declaration` and `test_cli_apply_scope_indexes_the_whole_repo_without_a_declaration` pin both behaviours.

**The default tier (nothing declared)**

- `whole_repo_scope` makes the repo root the single INPUT root.
- Excludes are what git already ignores, from `git ls-files --others --ignored --exclude-standard --directory`. Each nested git tree's own ignores are added, since the parent's listing cannot see through a submodule boundary.
- Dot directories, `__pycache__` and `node_modules` are pruned. The walk stops at depth 16 and records the directories it stopped at.
- Nested git trees are indexed, not excluded. `external.py` tags their rows afterward so they can be told apart in answers.
- The Doxyfile is not a tier. Since gh#333 its `INPUT` is treated as a documentation target, not a reasoning boundary. Its ALIASES and PREDEFINED still apply.
- The doxygen-guard `validate.exclude` list is not read. The docstring says the gate answers what must be documented, which is a different question from what should be indexed.
- After scope, `_drop_binary_files` classifies files by content and removes the binary ones. It does not go by extension.

**What "nothing declared" means in this repo**

`/…/self/repo/.clew.yaml` exists, but it only has a `guard:` section. `load_declaration_located` reads it and finds no `index_scope`, so the build takes the whole-repo tier. The log line reads "scope: indexing the WHOLE repository — no index_scope is declared … `.clew.yaml` exists but carries no index_scope". That means `tests/`, `scripts/` and `.venv/` are candidates for the index. The gate exempts them, but the index does not.

**Related**

- `derive_sub_indexes` splits a repo along its nested git trees, at any depth, and returns `[]` when there are none. Each tree gets its own sub-index, and its excludes name only its direct children.
- The `SCOPE_FROM_GUARD` spelling is kept for stored build metadata. `from-declaration` is the alias for it.

**Not verified**

I did not trace how the resolved roots become doxygen's `INPUT`/`FILE_PATTERNS` or which extensions tree-sitter parses. The `load_declaration_located` dossier also reported an anchor mismatch, so its body may differ slightly from the current file.