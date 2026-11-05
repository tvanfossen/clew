**Short answer:** the repository's own `index_scope:` declaration in `.clew.yaml` decides. If there isn't a usable one, the whole repository is the scope, minus what git ignores and minus dot and cache directories. A Doxyfile no longer decides scope. The decision lives in `clew/scope.py`, mainly `derive_scope` (line 639).

**Decision flow**

```
derive_scope(repo_root, stated?)
 │
 ├─ _declared_index_scope()
 │   ├─ no index_scope: section ───────────────┐
 │   ├─ section not a mapping ──────────┐      │
 │   ├─ unknown keys inside it ─────────┤      │
 │   │      (_Rejected, logged WARNING)  │      │
 │   ├─ roots listed, none exist ───────┤      │
 │   │      (missing roots dropped       │      │
 │   │       with a warning)             │      │
 │   └─ usable roots ──► DECLARED scope  │      │
 │                       (roots taken    │      │
 │                        at their word, │      │
 │                        never walked)  │      │
 │                                       ▼      ▼
 └─────────────────────────────► whole_repo_scope()
                                  root = the repo
                                  excludes = git-ignored paths
                                           + dot/cache dirs
                                  nested git trees INCLUDED
```

**The declared tier.** A declared `roots:` list is the only tier that narrows the index, and the roots are taken as written. Declared `excludes:` apply on top. The docs for `_declared_index_scope` say a clone of another repository sitting under a declared root is indexed with no walk to notice it. Paths that don't exist are dropped with a warning rather than handed to doxygen. Two cases fall through to the whole repository. One is a rejected section, meaning a non-mapping or an unknown key, which is logged. The other is a section where no root exists. The rejection is absorbed into the whole-repo tier so internal callers always get a usable scope. `declared_scope_rejection` is the separate build-time check that the CLI and MCP refresh paths use to refuse instead. The docs describe an excludes-only declaration as the case where this absorption caused a 900-second doxygen timeout.

**What happens when nothing is declared.** `whole_repo_scope` (line 683) is the default tier, not a last resort. Its single root is the whole repository, and it subtracts three things:

1. **Git-ignored paths.** `_gitignored_paths` runs `git ls-files --others --ignored --exclude-standard --directory` through `git_argv` and `git_env`, so a target's own git config cannot execute code. It also runs the same query inside each nested git tree, because the parent's `ls-files` stops at a submodule boundary.
2. **Dot and cache directories.** `_pruned_dirs` walks the tree. `_SKIP_DIR_NAMES` is `{__pycache__, node_modules}`. Dot directories are also skipped by `_skip_dir`, which I did not open. The walk stops descending at nested git trees, keeping only their top-level dot directories. It also stops at depth 16 (`_MAX_DEPTH`), and everything below that is taken wholesale and recorded.
3. **Nested git trees are not excluded.** Since gh#333 they are indexed and tagged by `external.py`, so a call that crosses into a vendored library is still traced.

**What the Doxyfile still does.** It no longer supplies `INPUT`. The Doxyfile is only a documentation target, and the docs use the measured Mbed-TLS case to show that honouring its `INPUT` indexed 1,571 headers and none of the 108 `library/*.c` implementations. The repo's Doxyfile still supplies `ALIASES` and `PREDEFINED`, and its `INPUT` is replaced. The doxygen-guard `files:` pattern is not a scope tier either, because it answers what must be documented, not what should be indexed.

**Things to know**

- **Outside git:** `_gitignored_paths` logs a warning and excludes nothing, so the scope is wider than the repo asked for.
- **Every derivation logs its reason.** The log says which tier was used and why, including the rejection text when a declaration was refused.
- **Stated options.** An embedding caller can pass a tier-1 `index_scope` at call time through `derive_scope(stated=…)`. It is built the same way as a declared one.

I did not open `_skip_dir` or `_INDEX_SCOPE_KEYS`, so the exact dot-directory rule and the full list of accepted keys are unverified here. `clew/scope.py` and `docs/languages/C_INTEGRATION.md` would settle both.