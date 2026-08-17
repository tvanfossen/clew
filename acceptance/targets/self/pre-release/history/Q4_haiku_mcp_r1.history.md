# Q4 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the index for information about how settings are combined from different sources.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"settings command line declaration override","note":"No matching symbols for 'settings command line declaration override'. This is NOT an error and NOT a malfor…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"doxyguard_db/buildoptions.py","kind":"file","file":"doxyguard_db/buildoptions.py","brief":"TIER 1, REACHABLE — one structured `options` argument for an embedding c…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"cli flag empty default inferred","note":"No matching symbols for 'cli flag empty default inferred'. This is NOT an error and NOT a malformed call, and it is NO…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** kind=file
- **got ⚠ error:** Error executing tool dossier: Subject kind 'file' names no dossier subject: a file has no dossier — its documentation is `search(corpus='prose')`.

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":3,"results":[{"file_path":"tests/test_buildoptions.py","heading":"tests/test_buildoptions.py — file-level documentation","snippet":"tests/test_>>buildoptions<<.py >>TIER<< 1, REACHABLE — g…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/buildoptions.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""TIER 1, REACHABLE — one structured `options` argument for an embedding caller. 3	 4	`.doxyguard-db.yaml` is TIER 2 and has been reachable since a declaration became 5	discoverable fr…

**Reasoning.** Now let me search for how the tiers interact and what determines precedence:

### 7. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"doxyguard_db/tiers.py","heading":"doxyguard_db/tiers.py — file-level documentation","snippet":"doxyguard_db/tiers.py Five->>tier<< >>precedence<< for every laye…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Five-tier precedence for every layered build option — ONE combination rule. 3	 4	`resolved = (tier1 or tier2 or tier5) union tier3 union tier4` 5	 6	In one line: **you can correct ou…

**Reasoning.** Now let me check what the CLI module says about empty values and how arguments are parsed:

### 9. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"tests/test_cli_surface.py","heading":"tests/test_cli_surface.py — file-level documentation","snippet":"tests/test_cli_surface.py The build CLI is SIX arguments,…

**Reasoning.** Let me search for the CLI module to understand how empty values are handled:

### 10. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"cli main entry_patterns exclude explicit","note":"No matching symbols for 'cli main entry_patterns exclude explicit'. This is NOT an error and NOT a malformed …

### 11. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"doxyguard_db/tiers.py","kind":"file","file":"doxyguard_db/tiers.py","brief":"Five-tier precedence for every layered build option — ONE combination rule. `resolved …

### 12. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""argparse + pipeline glue for `python -m doxyguard_db`. 3	 4	The pipeline runs in fixed order: 5	  1. doxygen → SQLite + XML 6	  2. copy_database to the user-specified --output path 7…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 300	## HOW EACH ONE IS NOW STATED, per group: 301	##   * `predefined`, `entry_patterns`, `shared_key_patterns`, `data_model`, `thread_patterns`, 302	##     `locks`, `mqtt_dispatch`, `dispatch`, `requirements`, `enrich` —…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 650	        ## for, so a warning would be invisible to it. 651	        if getattr(args, INDEX_SCOPE_SECTION, None): 652	            logger.error( 653	                "%s was stated but --scope is %r, and a stated %s is o…

**Reasoning.** Let me search for one more section on what empty means specifically:

### 15. `Bash`
- **asked:** command=cd ~/ddb-targets/self && grep -n "empty" doxyguard_db/tiers.py | head -20
- **got:** 276:    It says nobody stated a document, so the replaceable layer is empty and the

**Reasoning.** Perfect. Now I have enough information to answer the question comprehensively. Let me compile my answer based on what I've found:

## Answer

The rule that combines settings supplied in multiple ways is a **five-tier precedence system** with a specific combination rule that treats stated tiers (CLI and declaration) differently from accumulated tiers.

### The Five-Tier Precedence Rule

**Tier precedence (highest to lowest):**
1. **Tier 1 (Explicit)**: CLI flags / direct arguments passed to `build_index()` or `index(action='refresh')`
2. **Tier 2 (Declared)**: The target repository's own `.doxy

---

## Final answer as submitted

Perfect. Now I have enough information to answer the question comprehensively. Let me compile my answer based on what I've found:

## Answer

The rule that combines settings supplied in multiple ways is a **five-tier precedence system** with a specific combination rule that treats stated tiers (CLI and declaration) differently from accumulated tiers.

### The Five-Tier Precedence Rule

**Tier precedence (highest to lowest):**
1. **Tier 1 (Explicit)**: CLI flags / direct arguments passed to `build_index()` or `index(action='refresh')`
2. **Tier 2 (Declared)**: The target repository's own `.doxyguard-db.yaml` or `--declare` document
3. **Tier 3 (Target-fact)**: Facts someone else already wrote (Doxyfile ALIASES/PREDEFINED, manifests, language/platform entry points)
4. **Tier 4 (Ecosystem)**: Known-ecosystem signatures (UDM, ingot conventions)
5. **Tier 5 (Heuristic)**: Name-pattern matching (the floor, explicitly provisional)

**The combination rule (dossier:tiers.py:1-4):**

```
resolved = (tier1 or tier2 or tier5) union tier3 union tier4
```

**In plain language:** The resolved value is the **union of three parts**:
- The **stated layer**: whichever of tier 1, tier 2, or tier 5 has a value (in that priority order)
- **PLUS** tier 3 (target-fact) values, which **always accumulate** and cannot be removed by any statement
- **PLUS** tier 4 (ecosystem) values, which **always accumulate**

**Why this matters (dossier:tiers.py:19-23):** You can override the guesses (tier 5), but you cannot remove facts (tiers 3 and 4). Moving a setting from `.doxyguard-db.yaml` to a CLI flag does not accidentally lose other accumulated knowledge. For example, `entry_patterns` declared as `[%trampoline%]` plus the heuristic guesses `[main, app_main]` plus target facts `[app_run]` all combine into the final set `[app_run, main, app_main, %trampoline%]`.

### What an Empty Value on the Command Line Means

**An empty value is a WITHDRAWAL** (dossier:tiers.py:266-271 and dossier:cli.py:764-767):

- **Absent flag** (`None`): Inherits the next tier down (declared, then heuristic)
- **Empty value** (`[]` for lists, `{}` for documents): Explicitly withdraws tier 1, falling back to tier 2 (declaration) and then tier 5 (heuristic)
- **Non-empty value**: Replaces only the heuristic tier, leaving tier-3/4 facts untouched

**Three distinct states** are maintained:

For example, `--exclude` (cli.py:756-796):
- `--exclude` absent → inherits recorded exclusions from previous build
- `--exclude` with no values → withdraws all exclusions, emptying the stated tier
- `--exclude path1 path2` → replaces with these paths

The same pattern applies to all layered options (entry_patterns, shared_key_patterns, etc.).

**Implementation detail (tiers.py:354-358):** Empty sequences are falsy in Python, so `if explicit:` treats both `None` (absent) and `[]` (empty) as "nothing stated," causing both to fall through. The distinction is that `None` means "the flag was absent" while `[]` is explicitly passed and stamped into `build_meta` as a tier-1 statement with no explicit values, creating an auditable record of a withdrawal.

### Why This Matters

This design prevents the silent defect where **a valid setting applied and recorded but not read back gets discarded on the next refresh** (cli.py:757-762). By distinguishing absent (inherit), empty (withdraw), and stated (replace), an operator can:
- Leave a setting alone by omitting the flag
- Explicitly undo a previous statement by passing an empty value
- Override with a new value by passing it

All three outcomes are distinguished, recorded, and replayed consistently across builds.

---

## Gaps

None. The indexing system provided complete documentation of the precedence rule and empty-value semantics through:
- `doxyguard_db/tiers.py` — the formal five-tier combination rule and `resolve_layered()` implementation
- `doxyguard_db/cli.py` — the `_operator_excludes()` function exemplifying the three-state behavior
- `doxyguard_db/buildoptions.py` — tier-1 statement validation

The rule applies uniformly to all layered options: `entry_patterns`, `exclude`, `shared_key_patterns`, `data_model`, `thread_patterns`, `locks`, `mqtt_dispatch`, `dispatch`, `predefined`, `event_tags`, `vendored`, and `requirements`.
