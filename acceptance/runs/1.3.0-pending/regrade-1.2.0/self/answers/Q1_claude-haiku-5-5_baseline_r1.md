The index's file set is decided by one scope resolver, `derive_scope` in `clew/scope.py`, and then narrowed by a few later filters. With no declaration, the whole repository is the scope, minus what git ignores and minus dot- and cache-directories.

```
build (cli.py)
  │
  ├─ stated scope (tool call)? ──yes──► tier 1
  ├─ .clew.yaml index_scope:? ───yes──► tier 1 (roots/excludes)
  │                                      invalid → CLI refuses; internal callers fall through
  └─ neither ─────────────────────────► tier 2: whole repo, minus exclusions
        │
        ▼
  toolchain.toml [ignore].paths  → added to excludes (index tier only)
        ▼
  enumerate_tree: walk roots, prune excludes, no extension filter
        ▼
  binary files dropped → added to excludes
        ▼
  doxygen: INPUT = scope roots, FILE_PATTERNS forced to doxygen's default list
```

**1. Declared scope (tier 1).** `.clew.yaml` may carry `index_scope: {roots, excludes}` (`scope.py:612`, `_declared_index_scope`). Rules:
- `roots:` is required. `excludes:` alone is rejected.
- Roots that don't exist on disk are dropped.
- Unknown keys reject the whole declaration, so a typo can't be silently ignored.
- The CLI refuses with exit 1 on a rejected declaration (`cli.py:815`). Internal callers absorb it into the whole-repo tier with a WARNING.

**2. Nothing declared (tier 2).** `whole_repo_scope` (`scope.py:683`) makes the repo root the single INPUT root. Exclusions are:
- **Git-ignored paths.** `git ls-files --others --ignored --exclude-standard --directory`, run for the repo and for each nested git tree separately.
- **Dot-directories and `__pycache__`/`node_modules`.** These are pruned during the walk (`_pruned_dirs`, `_skip_dir`).
- **A depth guard.** Walks stop at 16 levels and the directory is recorded as depth-limited.

Nested git trees (submodules, vendored clones) are included, not excluded. `external.py` tags their rows afterward. A Doxyfile, if present, contributes ALIASES and PREDEFINED but no longer contributes INPUT (gh#333).

**3. Later filters, applied in both tiers:**
- `toolchain.toml` `[ignore].paths` globs are expanded into excludes (`cli.py:2529`). The `[clew.ignore]` section is gate-only and does not reach the index.
- `enumerate_tree` (`treescan.py:203`) walks roots and prunes excluded subtrees. It deliberately does not filter by extension, so any change under the scope invalidates the cache.
- Binary files are detected and dropped (`_drop_binary_files`, `filetypes.binary_files`).
- Doxygen's `FILE_PATTERNS` is forced to a fixed list (`doxygen.py:203`). That list is the real extension gate for doxygen-processed files; a repo cannot override it.

**What this means for this repo** (`acceptance/runs/1.2.0-pending/self/repo`):
- `.clew.yaml` declares only `guard:`, so this run takes tier 2.
- There is no `toolchain.toml`, no `suppress.toml` and no Doxyfile, so the only exclusions are `.gitignore` entries and dot/cache directories.
- Side effect: `.github/`, `.claude-plugin/` and `.pre-commit-hooks.yaml` are dot-paths and are pruned. Whether that is intended is a question for you.

**Caveat.** I traced the scope, enumeration and doxygen paths directly. I did not fully trace how non-doxygen languages (Rust, JS/TS) reach the harvester. `harvest.py` has its own extension sets and a `_parseable_file` check, but I did not confirm which files from the scope it receives. If you need that, I can trace it next.