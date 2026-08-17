# Q1 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the index to find where the file set for an external documentation tool is decided.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"doxyguard_db/scope.py","kind":"file","file":"doxyguard_db/scope.py","brief":"Resolve the index scope: a declaration, else the whole repository. TWO tiers, and the …

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":4,"results":[{"name":"tests/test_extra_input_patterns.py","kind":"file","file":"tests/test_extra_input_patterns.py","brief":"Tests for gh#3 — `--extra-input` silently defeated by the Do…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"scope derived file patterns","note":"No matching symbols for 'scope derived file patterns'. This is NOT an error and NOT a malformed call, and it is NOT a defi…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":4,"found":1,"subject":["DerivedScope","apply_scope","resolve_scope","effective_scope"],"results":[{"subject":"DerivedScope","subject_kind":"class","name":"doxyguard_db::scope::DerivedScope","ki…

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"scope.py function","note":"No matching symbols for 'scope.py function'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative eith…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject, target
- **got:** {"subject":"scope","subject_kind":"variable","name":"scope","rowid":388,"type":"DerivedScope","brief":"","version":"","provenance":null,"sites":[{"file":"doxyguard_db/propose/context.py","line":42,"signature":"DerivedSco…

### 7. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"resolved derive from_target","note":"No matching symbols for 'resolved derive from_target'. This is NOT an error and NOT a malformed call, and it is NOT a defi…

### 8. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"doxyguard_db/buildoptions.py","kind":"file","file":"doxyguard_db/buildoptions.py","brief":"TIER 1, REACHABLE — one structured `options` argument for an embedding c…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Resolve the index scope: a declaration, else the whole repository. 3	 4	TWO tiers, and the Doxyfile is no longer one of them (gh#333). The first is the 5	repo's own `index_scope:` — …

### 10. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"derive_scope","subject_kind":"function","name":"derive_scope","rowid":2869,"signature":" DerivedScope doxyguard_db.scope.derive_scope(Path repo_root, Path|str|None guard_config=None, dict|None stated=None)","…

### 11. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":3,"found":2,"subject":["_resolve_doxyfile_and_root","build_context","generate_doxygen"],"results":[{"subject":"_resolve_doxyfile_and_root","subject_kind":"function","name":"_resolve_doxyfile_an…

### 12. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"apply_scope doxygen INPUT","note":"No matching symbols for 'apply_scope doxygen INPUT'. This is NOT an error and NOT a malformed call, and it is NOT a definiti…

### 13. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossier","subject":"apply_scope","found":false,"note":"No dossier for 'apply_scope' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before concluding the sy…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""argparse + pipeline glue for `python -m doxyguard_db`. 3	 4	The pipeline runs in fixed order: 5	  1. doxygen → SQLite + XML 6	  2. copy_database to the user-specified --output path 7…

### 15. `Bash`
- **asked:** command=grep -n "INPUT" ~/ddb-targets/self/doxyguard_db/cli.py | head -20
- **got:** 600:## @param scope The scope whose roots become the INPUT list. 609:    @brief Make a derived scope the build's INPUT/EXCLUDE lists. 624:    declaration and makes it the INPUT list (`replace_input`), with any explicit 6…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 595	    sys.exit(1) 596	 597	 598	## @brief Fold a derived scope's roots and excludes into the build arguments. 599	## @param args Parsed CLI arguments (mutated in place). 600	## @param scope The scope whose roots become…

### 17. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":4,"results":[{"name":"doxyguard_db/ast_symbols.py","kind":"file","file":"doxyguard_db/ast_symbols.py","brief":"gh#11 — recover the function definitions doxygen never emitted. tree-sitte…

### 18. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"load_declaration","subject_kind":"function","name":"load_declaration","rowid":1813,"signature":" dict[str, Any] doxyguard_db.declaration.load_declaration(Path|str|None repo_root, Path|str|None guard_config=No…

### 19. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"load_declaration_located","subject_kind":"function","name":"load_declaration_located","rowid":1814,"signature":" tuple[dict[str, Any], Path | None] doxyguard_db.declaration.load_declaration_located(Path|str|N…

### 20. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/declaration.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""A target repo's own `.doxyguard-db.yaml` — its declared indexing conventions. 3	 4	doxyguard-db's central mandate is built-in defaults plus a DECLARED override, never a 5	hardcoded a…

### 21. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 194	## @brief The whole repository as one INPUT root, less only what git ignores. 195	## @param repo_root Repo root to index in full. 196	## @param guard_config Explicit guard-config path overriding discovery, or None. 1…

### 22. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/buildoptions.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""TIER 1, REACHABLE — one structured `options` argument for an embedding caller. 3	 4	`.doxyguard-db.yaml` is TIER 2 and has been reachable since a declaration became 5	discoverable fr…

**Reasoning.** Based on the index, I can now provide a complete answer about where the file set decision is made.

## Answer

The decision of what file set is handed to an external documentation tool (doxygen) is made through a **three-tier precedence system** implemented in `doxyguard_db/scope.py` and orchestrated in `doxyguard_db/cli.py`.

### The Decision is Made At:

**Primary orchestration:** `doxyguard_db/cli.py:622-677` in the `_apply_scope()` function, which calls `derive_scope_logged()` at line 672.

**Core logic:** `doxyguard_db/scope.py:166-191` in the `derive_scope()` function, which evaluates th

---

## Final answer as submitted

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
