Clew decides the file set in `clew/scope.py`, through two tiers: a repo's own declaration, or the whole repository. The index answers this from its docstrings and tests, not from a run of a build, so the behaviour below is what the code is documented to do.

**Decision flow**

```
build starts
  │
  ▼
derive_scope(repo_root)                       clew/scope.py:639
  │
  ├─ _declared_index_scope(root)              clew/scope.py:991
  │    reads .clew.yaml → index_scope: section
  │    ├─ no index_scope section      → None  (fall through)
  │    ├─ present but unusable        → _Rejected (see below)
  │    └─ usable                      → DerivedScope(source=declared,
  │                                       roots, excludes)
  │
  └─ no declaration → whole_repo_scope(root)  clew/scope.py:683
       roots = (repo_root,)
       excludes = git-ignored paths
                + nested trees' own ignores
                + dot and cache dirs
  │
  ▼
enumerate_tree(roots, excludes)               clew/treescan.py:203
  walks roots, pruning excluded subtrees during the walk
  no extension filter
```

**How a repo declares scope.** The only tier that is a decision about the index is `index_scope:` in the repo's `.clew.yaml`, with `roots:` and `excludes:`. Roots are repo-relative and taken at their word, never walked. A root that does not exist is dropped with a warning. Unknown keys inside `index_scope` are refused by name. `roots` is required: `excludes` alone does nothing. The `guard:` section and the doxygen-guard `files:` pattern do not supply index roots. A Doxyfile's `INPUT` is no longer a tier either (gh#333). The repo's Doxyfile still supplies aliases and predefines, but its `INPUT` is replaced, because it is a documentation target, not a reasoning boundary.

**What happens when nothing is declared.** The whole repository becomes the single root, less:

- what git ignores, collected with `git ls-files --ignored --exclude-standard`, through `git_argv`/`git_env` so the target's own git config cannot run commands;
- the same for each nested git tree, since a submodule's `.gitignore` is invisible to the parent;
- dot-directories and `__pycache__`/`node_modules` at any level, with the walk stopping at a nested tree's top level and at a depth of 16.

Nested clones and submodules are indexed, not excluded. `external.py` tags their rows afterwards so answers can still tell the codebases apart. The gate's `files:` pattern is not read here, because it answers what must be documented, not what should be indexed.

**Edge cases.**

- A `.clew.yaml` with `index_scope:` present but unusable (non-mapping, unknown keys, no existing roots) is `_Rejected`. The library-level `derive_scope` falls back to the whole repo and logs the rejection. The CLI refuses the build instead of silently widening it (`test_cli_apply_scope_refuses_a_rejected_declaration`).
- A malformed or unreadable `.clew.yaml` is logged at WARNING and treated as absent. An unknown top-level section raises `DeclarationError`, so a misspelling is never silently ignored.
- Stated scope from a tool call (tier 1) goes through the same construction as a written declaration, and only the reason text differs.

**Two points that surprise people.**

- Nothing is extension-filtered. `enumerate_tree` hands every file under the roots to the pipeline, so hashing and invalidation see any change. Files that no grammar handles are simply not indexed; the `files` inventory counts only what the index holds.
- A declared root is never walked, so a foreign clone inside it is indexed without being noticed. The design accepts that and relies on tagging.

One caveat: the index flagged the docstring of `load_declaration_located` (`clew/declaration.py:299`) as possibly out of date relative to its body. The behaviour described above comes from the other scope functions and their tests, which are current.