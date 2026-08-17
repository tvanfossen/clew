# Q1 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":5,"results":[{"name":"test_cli_apply_scope_default_replaces_the_doxyfile_input","kind":"function","file":"tests/test_scope.py","brief":"The parser default is from-guard, so a bare invoc…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** kind=file
- **got ⚠ error:** Error executing tool dossier: Subject kind 'file' names no dossier subject: a file has no dossier — its documentation is `search(corpus='prose')`.

### 3. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":4,"found":3,"subject":["derive_scope","is_derived","DerivedScope","resolve_scope"],"results":[{"subject":"derive_scope","subject_kind":"function","name":"derive_scope","rowid":2869,"signature":…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":6,"found":6,"subject":["_declared_index_scope","whole_repo_scope","build_context","build_argv","_scope_provenance","_resolve_doxyfile_and_root"],"results":[{"subject":"_declared_index_scope","s…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["_apply_scope","_run_pipeline"],"results":[{"subject":"_apply_scope","subject_kind":"function","name":"_apply_scope","rowid":5921,"signature":"_apply_scope(args: argparse…

### 6. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"replace_input INPUT","note":"No matching symbols for 'replace_input INPUT'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative …

### 7. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"apply_options INPUT","note":"No matching symbols for 'apply_options INPUT'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative …

### 8. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["_fold_scope_into_args","_operator_excludes"],"results":[{"subject":"_fold_scope_into_args","subject_kind":"function","name":"_fold_scope_into_args","rowid":5920,"signatu…

### 9. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":4,"results":[{"name":"test_build_doxyfile_appends_extra_input_clears_exclude","kind":"function","file":"tests/test_build_docs_db.py"},{"name":"extra_input_clears_exclude","kind":"functi…

### 10. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":4,"results":[{"name":"_build_doxyfile_content","kind":"function","file":"doxyguard_db/doxygen.py","brief":"Build the augmented Doxyfile content piped to doxygen on stdin."},{"name":"tes…

### 11. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"subject":"_build_doxyfile_content","subject_kind":"function","name":"_build_doxyfile_content","rowid":1896,"signature":" str doxyguard_db.doxygen._build_doxyfile_content(Path doxyfile, list[str]|None extra_input, list[…

### 12. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"SCOPE_FROM_GUARD choices","note":"No matching symbols for 'SCOPE_FROM_GUARD choices'. This is NOT an error and NOT a malformed call, and it is NOT a definitive…

**Reasoning.** ## Answer

**Where the decision is made:** `derive_scope()` in `doxyguard_db/scope.py:168-193` is the single function that decides the file set (INPUT roots + excludes) handed to doxygen. It is called from `_apply_scope()` in `doxyguard_db/cli.py:622-677`, which is the pipeline step that turns the decision into concrete `INPUT`/`EXCLUDE` entries fed to the Doxyfile.

### The inputs, in the order they're consulted, and which one wins

1. **`--scope` gate** (`doxyguard_db/cli.py:622-677`, `_apply_scope`). The whole scope-derivation path only runs when `args.scope == SCOPE_FROM_GUARD` (the defaul

---

## Final answer as submitted

## Answer

**Where the decision is made:** `derive_scope()` in `doxyguard_db/scope.py:168-193` is the single function that decides the file set (INPUT roots + excludes) handed to doxygen. It is called from `_apply_scope()` in `doxyguard_db/cli.py:622-677`, which is the pipeline step that turns the decision into concrete `INPUT`/`EXCLUDE` entries fed to the Doxyfile.

### The inputs, in the order they're consulted, and which one wins

1. **`--scope` gate** (`doxyguard_db/cli.py:622-677`, `_apply_scope`). The whole scope-derivation path only runs when `args.scope == SCOPE_FROM_GUARD` (the default). If the caller sets `--scope` to something else *and* also states an `index_scope`, the build refuses outright (`cli.py:645-655`) rather than silently discarding the statement — a deliberate fail-closed choice (gh#382).

2. **Tier 1 — a "stated" `index_scope` passed programmatically** (e.g. by an embedding caller/MCP tool). Read in `_declared_index_scope()` (`doxyguard_db/scope.py:416-483`, lines 448-450): if `stated` is truthy it is used directly, built through the *same* construction as a written declaration — it just wins first and reports a different `reason` ("stated by the caller (tier 1)").

3. **Tier 2 — the repo's own `.doxyguard-db.yaml` `index_scope:` section** (`roots:` / `excludes:`), discovered via `load_declaration_located()` (`scope.py:459`). This also reaches a scope declared inside a guard config's `x-doxyguard-db` passthrough (gh#16), not just the repo-root file. Roots that don't exist on disk are silently dropped (`_existing_paths`); if nothing usable survives, this tier returns `None` and control falls through.

4. **Tier 3 — the whole-repo default**, `whole_repo_scope()` (`doxyguard_db/scope.py:200-244`) — this is what happens when the repo states nothing at all (see below).

`derive_scope()` itself (`scope.py:193`) expresses the precedence in one line:
```python
return _declared_index_scope(root, guard_config, stated) or whole_repo_scope(root, guard_config)
```
So: **stated ⟶ declared ⟶ whole-repo**, first non-empty wins. Note the Doxyfile's own `INPUT`/`FILE_PATTERNS` is explicitly **not** a tier anymore — `scope.py:174-179` documents that "THE DOXYFILE FALLBACK IS GONE (gh#333)": a Doxyfile still supplies `ALIASES`/`PREDEFINED`, but never the file set.

5. **The winning `DerivedScope` is folded into `args.extra_input`/`args.extra_exclude`** by `_fold_scope_into_args()` (`cli.py:603-614`), which also sets `args.replace_input = True`.

6. **Operator narrowing, applied after and on top of the derived scope**: `_operator_excludes()` (`cli.py:756-796`) resolves an explicit `--exclude`, or (if `--exclude` wasn't passed this time) replays what a previous build recorded, or an empty list explicitly withdraws it (three-state logic at `cli.py:781-786`). These are appended to `args.extra_exclude` in `_run_pipeline` (`cli.py:2076-2078`), i.e. *after* the derived-scope excludes, so operator excludes can only shrink the set further, never widen it back.

7. **`--extra-input`/`--extra-exclude` CLI flags** are also folded in, with the derived scope's roots prepended ahead of them (`cli.py:612`: `args.extra_input = [scope.roots] + args.extra_input`).

8. **Final write to the Doxyfile** happens in `_build_doxyfile_content()` (`doxyguard_db/doxygen.py:519-594`). Because `replace_input` is true whenever a from-guard scope was folded, it clears the Doxyfile's own `INPUT` and `EXCLUDE_PATTERNS` (lines 573-583: `"INPUT =\n"`, `"EXCLUDE_PATTERNS =\n"`) and re-adds only the resolved roots (`INPUT += <path>`) and excludes — so a repo-shipped Doxyfile can never silently re-admit or drop scope once `replace_input` fires.

### What happens when a repository states nothing at all

`whole_repo_scope()` (`doxyguard_db/scope.py:200-244`) is used. It:
- roots the scope at the entire repository (`roots=(root,)`, line 230),
- subtracts everything git ignores — on **both sides of every nested-repo/submodule boundary** (lines 223-227: `_gitignored_paths` is called once for the root and again per `nested_repo_roots`),
- subtracts dot/cache directories (`_pruned_dirs`, line 228),
- deliberately **includes** nested git trees (submodules) rather than excluding them — since gh#333 those are indexed and tagged afterward by `external.py` instead of being cut out at scope time (documented at `scope.py:206-210`),
- and does **not** consult the doxygen-guard gate, because that gate answers "what must be documented," a different question from "what should be indexed" (`scope.py:213-215`).

The resulting `reason` string (`scope.py:231-238`) records explicitly that no `index_scope` was declared and that any Doxyfile the repo ships still only supplies `ALIASES`/`PREDEFINED`, not `INPUT`.

## Gaps

- I did not read the exact set of `--scope` choices other than `SCOPE_FROM_GUARD` (a search for the argparse `choices=` definition came back empty on tokens tried); this doesn't affect the answer since the from-guard path is the default and the one that performs scope derivation, but I can't name the alternative values without reading `cli.py`'s argument parser directly.
- I traced the "operator excludes" and "extra-input/extra-exclude" folding from function bodies and docstrings rather than executing the pipeline, so the exact list-ordering guarantee (which entries end up first in the final `INPUT +=`/`EXCLUDE +=` sequence) is based on the code as read, not on an observed build.
