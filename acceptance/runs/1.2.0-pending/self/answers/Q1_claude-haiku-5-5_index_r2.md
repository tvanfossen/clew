Two things decide what gets indexed: the repository's own `.clew.yaml` declaration, and, when there is none, the whole tree minus what git ignores. A Doxyfile no longer decides scope.

**The decision flow**

```
build (--scope from-declaration; spelled from-guard in recorded builds)
  │
  ▼
cli._apply_scope ──► scope.derive_scope(repo_root)
                       │
                       ├─ _declared_index_scope
                       │     reads .clew.yaml via declaration.load_declaration_located
                       │     ├─ no index_scope section ──────────────► None (fall through)
                       │     ├─ section present but unusable ────────► _Rejected
                       │     │     (not a mapping, unknown key, no usable roots)
                       │     └─ usable ─► DerivedScope(roots, excludes), source=declared
                       │
                       └─ whole_repo_scope  (the default tier)
                             roots    = (repo_root,)
                             excludes = git-ignored paths (both sides of every
                                        submodule boundary) + dot/cache dirs
  │
  ▼
_fold_scope_into_args ──► roots/excludes become the doxygen INPUT
  │                       (repo's Doxyfile kept for ALIASES/PREDEFINED only)
  ▼
_scanned_files (no-doxygen path, e.g. Rust/JS/TS) ──► enumerate_tree(roots, excludes)
```

**What happens when a repo declares an `index_scope`**

- `roots` is required. It replaces the default scope, and each root must exist on disk or it is dropped. `excludes` alone does nothing.
- Declared roots are taken at their word and never walked, so a clone nested under a declared root is indexed without being noticed. `external.py` walks for nested trees after the build and tags their rows.
- A section that is present but unusable is refused with exit 1 at build time (`cli._apply_scope`), rather than quietly falling back to the whole repository. An unknown key inside the section is refused the same way, and an unknown top-level section name raises `DeclarationError`.

**What happens when nothing is declared**

This is the default tier, and it is deliberately wide:

1. **Root:** the whole repository, with nested git trees included. Nested trees are tagged, not excluded (gh#333).
2. **Git-ignored paths:** `git ls-files --others --ignored --exclude-standard --directory` removes them. Each nested repo's own `.gitignore` is consulted separately, because the parent cannot see through a submodule boundary. Git runs with `git_env()` and `git_argv`, so a target's `.git/config` cannot execute code.
3. **Dot and cache directories:** `_skip_dir` drops any name starting with `.`, plus `__pycache__` and `node_modules`. The walk stops at nested trees, keeping only their top-level dot directories. Directories deeper than 16 levels are taken wholesale and recorded in `_DEPTH_LIMITED`.
4. **Doxyfile:** if the repo ships one, it still supplies ALIASES, PREDEFINED and filters, but its INPUT is replaced. The reason is measured: Mbed-TLS's `mbedtls.doxyfile` sets `INPUT = ../include` and `FILE_PATTERNS = *.h`, which indexes 1,571 header declarations and none of its 108 `library/*.c` implementations.
5. **doxygen-guard's `files:` pattern is not a tier.** It answers what must be documented, not what should be indexed.
6. **No Doxyfile and no declaration:** `cli._resolve_doxyfile_and_root` synthesizes a minimal Doxyfile. Scope is still decided by `derive_scope`, not by the synthesis.

The reason string names the fallback: "no index_scope is declared for this repo — … so the whole repository is the index scope."

**Caveat:** the index flagged `load_declaration_located` (`clew/declaration.py:299`) as anchor-mismatched, so its line span may have moved since the last build. I read its body from the index, not from the current file.