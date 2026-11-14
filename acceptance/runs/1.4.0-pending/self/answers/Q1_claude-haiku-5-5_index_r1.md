**Short answer:** the index's file set is decided in `clew/scope.py`. A declared `index_scope` in `.clew.yaml` sets the roots, and if none is usable the whole repository is the scope. Which files then produce rows depends on each harvester's extension list. Files in scope that no harvester claims are reported as "not indexed," not dropped silently.

```
.clew.yaml (repo root only)
   │  index_scope: present and usable?
   ├─ yes ──► roots (repo-relative, must exist) + excludes  ──┐
   └─ no  ──► whole_repo_scope: root = repo, excludes = ───────┤
              git-ignored paths + dot/cache dirs               │
                                                               ▼
                                   _fold_scope_into_args → build INPUT/EXCLUDE
                                   (replaces the Doxyfile's INPUT)
                                                               ▼
                       per-harvester extension tables decide which in-scope files get rows
                                                               ▼
                       in-scope files with no rows → "not_indexed" (ext=count)
```

**1. The declaration.** `derive_scope` (`clew/scope.py:639`) first checks for a stated scope from an MCP caller, then `<root>/.clew.yaml` via `load_declaration_located` (`clew/declaration.py:299`). Only the repo root is read. The `index_scope:` section takes `roots` and `excludes`. Roots are repo-relative. The rules:
- `roots` is required; `excludes` alone does nothing.
- A root that does not exist is dropped with a warning.
- An absolute or `../` entry that escapes the repo is refused (`_existing_paths`).
- An unknown key inside `index_scope` is refused by name, and an unknown top-level section fails the build. The `guard:` section is stripped out and does not affect the index.

**2. Nothing declared.** A missing `.clew.yaml`, or one with no `index_scope:`, falls through to `whole_repo_scope` (`scope.py:683`). The scope's reason string says which case applied: "no `.clew.yaml` was found at …" or "exists but carries no `index_scope`." A declaration that is present but unusable also falls through, with the rejection reason carried into the reason string. `declared_scope_rejection` lets the CLI and MCP refresh refuse such a build instead of absorbing it. The old Doxyfile fallback is gone (gh#333). A Doxyfile still supplies ALIASES and PREDEFINED, but not INPUT.

**3. What the whole-repo tier includes and excludes.**
- Included: the entire tree, including nested git clones. `external.py` tags their rows afterwards so they stay distinguishable.
- Excluded, in two parts:
  - Anything git ignores, via `git ls-files --others --ignored --exclude-standard --directory`, run through `git_argv`/`git_env` so a target's own `.git/config` cannot execute code. This is applied on both sides of every nested-repo boundary.
  - Dot and cache directories, found by walking the tree (`_pruned_dirs`, `scope.py:908`). The walk stops at nested git trees and at a depth limit, and the depth-limited directories are recorded.

This repo's status shows the excludes as `.git, .claude-plugin, .github`, which is the dot-directory rule at work.

**4. Folding into the build.** `_fold_scope_into_args` (`clew/cli.py:739`) writes the roots into INPUT, the excludes into EXCLUDE, and sets `replace_input`. Every tier goes through this one function.

**5. Which in-scope files get rows.** This is decided by extension, per harvester, not by the scope. The tables are `harvest._CPP_EXTS`, `_PY_EXTS`, `_TS_EXTS`, `synth.SYNTH_EXTS`, doxygen's `.c`/`.h`, and rustdoc's `.rs`. A file in scope with no claiming extension yields no rows. The build records those file types as `not_indexed` (`_not_indexed_scope`, `clew/cli.py`), and an extensionless file is named "(no extension)." That record is what stops an empty answer being read as absence.

**This repo's current state** (from `index(action='status')`):
- No `index_scope` is declared, so the whole repository is the scope.
- 435 files are in scope and 397 are indexed.
- 14 files are listed as not indexed by extension: 3 extensionless, 3 `.csv`, 2 `.rs`, 2 `.toml`, and 1 each of `.jsonl`, `.lock`, `.motor` and `.sql`.

Two things I did not settle:
- The 14 listed files account for only part of the 38-file gap between 435 and 397, and I did not trace the remainder.
- Two `.rs` files are listed as not indexed even though rustdoc claims `.rs`. I did not find out why.

I also could not run `propose_declaration`, because its permission was not granted, so I did not check what a proposed declaration would change. `load_declaration_located` reported a line-anchor mismatch against the build, so its body may be slightly out of date; the behaviour I describe above comes from its docstring and the tests named in the index.