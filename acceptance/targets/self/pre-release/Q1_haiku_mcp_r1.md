# Q1 — mcp — haiku — run 1

Based on the index, I can now provide a complete answer about where the file set decision is made.

## Answer

The decision of what file set is handed to an external documentation tool (doxygen) is made through a **three-tier precedence system** implemented in `doxyguard_db/scope.py` and orchestrated in `doxyguard_db/cli.py`.

### The Decision is Made At:

**Primary orchestration:** `doxyguard_db/cli.py:622-677` in the `_apply_scope()` function, which calls `derive_scope_logged()` at line 672.

**Core logic:** `doxyguard_db/scope.py:166-191` in the `derive_scope()` function, which evaluates the three tiers.

### The Three Inputs and Their Priority Order:

**TIER 1 (STATED) — Highest Priority:**
- Parameter: CLI argument `--index_scope` or programmatic `stated` dict parameter
- Location: `doxyguard_db/cli.py:675` — passed as `getattr(args, INDEX_SCOPE_SECTION, None)` to `derive_scope_logged()`
- Implementation: `doxyguard_db/scope.py:451-458` in `_declared_index_scope()`
- Reason statement: "stated by the caller (tier 1)" at line 475

**TIER 2 (DECLARED) — Medium Priority:**
- Declaration file: `.doxyguard-db.yaml` at repo root (preferred) OR `x-doxyguard-db` passthrough in `.doxygen-guard.yaml`
- Location: `doxyguard_db/declaration.py:281-339` in `load_declaration_located()` determines which file is read
- Details: The `index_scope:` section with `roots:` and `excludes:` keys (see lines 419-421 of scope.py for example format)
- Specific implementation: `doxyguard_db/scope.py:414-481` in `_declared_index_scope()` 
- Source constant: `SOURCE_DECLARED = "doxyguard-db-declaration"` at line 78 of scope.py

**TIER 3 (DEFAULT/FALLBACK) — When Nothing Above is Declared:**
- The entire repository becomes the root, with exclusions
- Location: `doxyguard_db/scope.py:200-242` in `whole_repo_scope()`
- Source constant: `SOURCE_WHOLE_REPO = "whole-repo"` at line 74 of scope.py

### What Gets Handed to Doxygen:

The resolved scope becomes `roots=` and `excludes=` which are folded into `args.extra_input` and `args.extra_exclude` at `doxyguard_db/cli.py:612-614` in the `_fold_scope_into_args()` function, with `args.replace_input = True` at line 614, which replaces the Doxyfile's own INPUT entirely (documented rationale: gh#333 at cli.py:2260).

### When a Repository States Nothing At All:

The whole repository becomes the index scope, as returned at `doxyguard_db/scope.py:230-242`, with:
- **Single root:** `roots=(root,)` — the repository root itself (line 240)
- **Exclusions from:**
  1. Paths git ignores: `_gitignored_paths(root)` at line 222 (via `git ls-files --others --ignored --exclude-standard --directory`)
  2. Nested git trees' own ignored paths: loop at lines 227-228
  3. Dot-directories and cache directories: `_pruned_dirs()` at line 229 (excludes paths matching `_skip_dir()` at line 401, which catches `.git`, `__pycache__`, `node_modules`)

The reason logged (line 232-238) explicitly states: "no `index_scope` is declared for this repo — [searched locations] — so the whole repository is the index scope, INCLUDING any nested git trees, less the paths git ignores and the dot/cache directories."

---

## Gaps

None encountered. The index provided complete information about all three decision tiers, their priority order, the exact functions that implement them, and the file handling for the default case.
