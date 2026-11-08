**Short answer:** the file set is decided by one resolver, `clew/scope.py`. A repo that declares `index_scope:` in its `.clew.yaml` gets exactly those roots. A repo that declares nothing gets the whole repository, minus what git ignores and minus dot and cache directories. There is no Doxyfile tier any more.

```
build starts
   │
   ▼
derive_scope(repo_root, stated?)          clew/scope.py:639
   │
   ├─ tier 1: stated by caller (MCP options)  ─┐
   ├─ tier 2: .clew.yaml  index_scope:         ├─► _declared_index_scope  (scope.py:991)
   │                                          ─┘     usable? → DerivedScope(source=declared)
   │                                                 malformed? → _Rejected → whole repo, reason says why
   │
   └─ nothing declared ─► whole_repo_scope       (scope.py:683)
                              roots    = (repo_root,)
                              excludes = git-ignored paths
                                         + nested-repo ignores
                                         + dot/cache dirs (_pruned_dirs)
```

**When something is declared (tier 2)**

- The section is `index_scope:` with `roots:` (required, repo-relative) and an optional `excludes:`.
- Each root is checked against disk. A root that doesn't exist is dropped. If no root survives, the declaration is rejected.
- Unknown keys are rejected by name. `exclude:` for `excludes:` is refused rather than silently ignored.
- A declared root is taken at its word and never walked. A nested clone under it is indexed without being noticed. `external.py` tags those rows afterwards so they stay distinguishable.
- The `reason` names the file it was read from, or the caller for a stated scope.

**When nothing is declared (the default)**

- The scope is the whole repository, including nested git trees. The reason is logged at WARNING, so an unchosen boundary is never mistaken for a chosen one.
- Excluded are the paths `git ls-files --others --ignored --exclude-standard` reports, collected from the parent and from each nested repo. Git is queried through `git_argv`/`git_env` so a cloned repo's `.git/config` can't run code.
- The walk also excludes any directory whose name starts with `.`, plus `__pycache__` and `node_modules` (`_SKIP_DIR_NAMES`). It stops at a nested git tree, keeping that tree's own top-level dot directories, and stops at depth 16 with the cut-off directories recorded.
- If git is missing or the tree isn't a repo, nothing is excluded and a warning says so. The scope is wider than intended, not empty.

**Where the file set is consumed**

- For a doxygen build, the derived roots and excludes feed doxygen's INPUT and EXCLUDE.
- For a parse-built target (Rust, JS/TS), where there is no doxygen enumeration, `_scanned_files` in `clew/cli.py:2483` reads the exact `DerivedScope` the build applied and walks it under the same excludes. Otherwise a `node_modules` or vendored tree could be published even though the owner declared a narrower scope.

**Doxyfile role**

The repo's Doxyfile is still read, but only for ALIASES, PREDEFINED and similar settings. Its `INPUT` is ignored (gh#333). The reason is that a Doxyfile documents the published API, and using its INPUT as the reasoning boundary meant a repo that documented itself got a smaller index. On Mbed-TLS, honouring `INPUT = ../include` indexed headers and none of the `library/*.c` implementations.

**Stale comments to fix**

`_declared_index_scope`'s docstring still says a missing declaration "drops the resolution to the Doxyfile's own INPUT". That contradicts `derive_scope`, which now goes straight to the whole repo. I read the code, not the behaviour at runtime, so I did not confirm the fallback path with a build. The `_skip_dir` comment about "cache directories" is also broader than the two names in `_SKIP_DIR_NAMES`, since the rule also covers every dot-directory.