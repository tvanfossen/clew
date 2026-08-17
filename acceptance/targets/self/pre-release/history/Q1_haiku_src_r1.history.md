# Q1 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll explore this repository to find where it decides what file set to hand to an external documentation tool.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "*.py" | head -20
- **got:** ~/ddb-targets/self/acceptance/bench/rescore_audit.py ~/ddb-targets/self/acceptance/bench/fallback_audit.py ~/ddb-targets/self/acceptance/bench/arm_headroom.py ~/ddb-targets/self/acceptance/bench/bench_arms.py ~/ddb-targe…

### 2. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f \( -name "*.yaml" -o -name "*.yml" -o -name "Doxyfile" -o -name "*.json" \) | head -20
- **got:** ~/ddb-targets/self/acceptance/targets/entropic/pre-release/Q9_sonnet_mcp_r1.grade.json ~/ddb-targets/self/acceptance/targets/entropic/pre-release/argv/Q1_haiku_src_r1.json ~/ddb-targets/self/acceptance/targets/entropic/p…

### 3. `Bash`
- **asked:** command=find ~/ddb-targets/self -type d -name "doxyguard_db" | head -5
- **got:** ~/ddb-targets/self/doxyguard_db

### 4. `Bash`
- **asked:** command=find ~/ddb-targets/self/doxyguard_db -type f -name "*.py" | sort
- **got:** ~/ddb-targets/self/doxyguard_db/ast_symbols.py ~/ddb-targets/self/doxyguard_db/buildoptions.py ~/ddb-targets/self/doxyguard_db/callback_edges.py ~/ddb-targets/self/doxyguard_db/call_edges.py ~/ddb-targets/self/doxyguard_…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Resolve the index scope: a declaration, else the whole repository. 3	 4	TWO tiers, and the Doxyfile is no longer one of them (gh#333). The first is the 5	repo's own `index_scope:` — …

**Reasoning.** Now let me check the declaration module to see all the places a declaration can come from:

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/declaration.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""A target repo's own `.doxyguard-db.yaml` — its declared indexing conventions. 3	 4	doxyguard-db's central mandate is built-in defaults plus a DECLARED override, never a 5	hardcoded a…

**Reasoning.** Now let me check how this scope decision is passed to doxygen:

### 7. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/doxygen.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Doxygen invocation, output handling, and Doxyfile parsing. 3	 4	`run_doxygen` spawns the doxygen binary with our augmented Doxyfile, 5	streams its stdout to drive a Rich progress bar…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/harvest_plan.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""The ten per-file AST stages of one build, assembled before any of them runs. 3	 4	gh#358. Every stage here walks the same file set and each used to drive its own 5	`run_harvest`, so …

### 9. `Bash`
- **asked:** command=grep -rn "INPUT\s*=" ~/ddb-targets/self/doxyguard_db/*.py | head -20
- **got:** ~/ddb-targets/self/doxyguard_db/cli.py:2265:        # and `INPUT = ../include`, because it publishes an API reference. Honouring that ~/ddb-targets/self/doxyguard_db/declaration.py:202:## mbedtls's own file sets `FILE_PA…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/doxygen.py
- **got:** 450	## @param output_dir Absolute directory doxygen writes sqlite3/xml into (becomes OUTPUT_DIRECTORY); the Doxyfile is written here too, so its parent is a valid work_dir. 451	## @return Path to the written Doxyfile. 45…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/treescan.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""File-identity hashing and indexed-tree enumeration for incremental builds. 3	 4	Split from `indexcache` by responsibility: this module answers "what files does 5	this build read, and…

### 12. `Bash`
- **asked:** command=grep -rn "extra_input\|doxygen_input_roots" ~/ddb-targets/self/doxyguard_db/*.py | head -30
- **got:** ~/ddb-targets/self/doxyguard_db/cli.py:183:    doxygen_input_roots, ~/ddb-targets/self/doxyguard_db/cli.py:305:##   * `extra_input` / `extra_exclude` — absorbed by `index_scope:` (`roots:` / `excludes:`), ~/ddb-targets/s…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 600	## @param scope The scope whose roots become the INPUT list. 601	## @version 1 602	## @req REQ-DDB-CLI-001 603	def _fold_scope_into_args(args: argparse.Namespace, scope: DerivedScope) -> None: 604	    """ONE fold for…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 640	    @brief Resolve the build's file scope from the requested source. 641	    @version 7 642	    """ 643	    args.replace_input = False 644	    if args.scope != SCOPE_FROM_GUARD: 645	        ## gh#382 — REFUSE the con…

**Reasoning.** Now let me check the treescan to see what `doxygen_input_roots` returns:

### 15. `Bash`
- **asked:** command=grep -n "def doxygen_input_roots" ~/ddb-targets/self/doxyguard_db/treescan.py
- **got:** 338:def doxygen_input_roots(

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/treescan.py
- **got:** 338	def doxygen_input_roots( 339	    doxyfile: Path, 340	    work_dir: Path, 341	    extra_input: list[str] | None, 342	    extra_exclude: list[str] | None, 343	    replace_input: bool = False, 344	) -> tuple[list[Path],…

**Reasoning.** Now let me verify the exact behavior when nothing is declared by reviewing the key code one more time:

### 17. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 160	## @brief Resolve the index scope: a declared index_scope, else the whole repository. 161	## @param repo_root Repo root to resolve scope for. 162	## @param guard_config Explicit guard-config path overriding discovery…

**Reasoning.** Perfect! Now I have all the information needed. Let me compile the comprehensive answer.

---

## ANSWER

This program decides what file set to hand to doxygen through a **scope resolution** system. The decision is made in one location and has a clear precedence hierarchy for inputs.

### WHERE THE DECISION IS MADE

**Primary:** `doxyguard_db/scope.py:166-191` — the `derive_scope()` function  
**Entry point:** `doxyguard_db/cli.py:622-677` — the `_apply_scope()` function that invokes it

### EVERY INPUT THAT CAN INFLUENCE THE DECISION

The file set is determined by exactly **one input at a tim

---

## Final answer as submitted

Perfect! Now I have all the information needed. Let me compile the comprehensive answer.

---

## ANSWER

This program decides what file set to hand to doxygen through a **scope resolution** system. The decision is made in one location and has a clear precedence hierarchy for inputs.

### WHERE THE DECISION IS MADE

**Primary:** `doxyguard_db/scope.py:166-191` — the `derive_scope()` function  
**Entry point:** `doxyguard_db/cli.py:622-677` — the `_apply_scope()` function that invokes it

### EVERY INPUT THAT CAN INFLUENCE THE DECISION

The file set is determined by exactly **one input at a time**, chosen from a four-tier hierarchy:

#### **Tier 1 (Highest Priority):** Stated `index_scope` via CLI parameter
- **How passed:** `--declare '{"index_scope": {"roots": [...]}}'` or equivalent  
- **Where used:** `doxyguard_db/cli.py:675` passes `getattr(args, INDEX_SCOPE_SECTION, None)` as the `stated` parameter to `derive_scope()`  
- **Code location:** `doxyguard_db/scope.py:451-458` — checked first in `_declared_index_scope()`  
- **Example:** `{"roots": ["src", "include"], "excludes": ["tests"]}`

#### **Tier 2:** `.doxyguard-db.yaml` file in repository root
- **Where read:** `doxyguard_db/declaration.py:310` — `root / DECLARATION_NAME` where `DECLARATION_NAME = ".doxyguard-db.yaml"`  
- **What it contains:** A YAML file with an `index_scope:` section  
- **Example file format:**
  ```yaml
  index_scope:
    roots:
      - src
      - include
    excludes:
      - tests/fixtures
  ```
- **Code location:** `doxyguard_db/declaration.py:262-269` reads this file via `load_declaration()`

#### **Tier 3:** `x-doxyguard-db` passthrough section in `.doxygen-guard.yaml`
- **Where discovered:** `doxyguard_db/declaration.py:326` — reads the discovered guard config  
- **What it contains:** The same `index_scope:` structure nested under `x-doxyguard-db:` in the repo's existing doxygen-guard config  
- **Example:**
  ```yaml
  x-doxyguard-db:
    index_scope:
      roots:
        - src
  ```
- **Code location:** `doxyguard_db/declaration.py:523-574` — `_passthrough_declaration()` extracts it

#### **Tier 4 (Fallback):** Whole repository (when nothing is declared)
- **Code location:** `doxyguard_db/scope.py:200-242` — `whole_repo_scope()`  
- **Roots:** The repository root directory itself  
- **Excludes automatically:** All paths that git ignores, dot-directories (`.*/`), and cache directories (`__pycache__`, `node_modules`)

### WHICH ONE WINS

The precedence is absolute and strictly ordered:

```
Tier 1 (stated) → Tier 2 (.doxyguard-db.yaml) → Tier 3 (x-doxyguard-db) → Tier 4 (whole repo)
```

At `doxyguard_db/scope.py:191`:
```python
return _declared_index_scope(root, guard_config, stated) or whole_repo_scope(root, guard_config)
```

The `or` operator means: **if `_declared_index_scope()` returns a truthy value (Tier 1-3), use it; otherwise use the whole repository (Tier 4).**

At `doxyguard_db/declaration.py:279-337`, the declaration loading checks tiers in order:
1. Line 451-458: Check `stated` parameter first
2. Line 310-311: Check `.doxyguard-db.yaml` file second
3. Line 313-326: Check `x-doxyguard-db` passthrough third
4. Returns `({}, None)` if none exist, triggering the Tier 4 fallback

### WHAT HAPPENS WHEN THE REPOSITORY STATES NOTHING AT ALL

When all four tiers yield nothing:

1. **The whole repository becomes the index scope** (`doxyguard_db/scope.py:191, 200-242`)

2. **Single root:** The repository root itself (line 240: `roots=(root,)`)

3. **Automatic excludes are derived from:**
   - `doxyguard_db/scope.py:222` — paths the repository's `.gitignore` files list (via `_gitignored_paths()`)
   - `doxyguard_db/scope.py:229` — **nested git repositories' own `.gitignore` files** (via nested loop checking each submodule/clone)
   - `doxyguard_db/scope.py:229` — dot-directories and cache directories via `_pruned_dirs()`

4. **Result passed to doxygen:**
   - At `doxyguard_db/cli.py:612`, the roots become `args.extra_input`  
   - At `doxyguard_db/doxygen.py:568, 582`, they become `INPUT +=` lines in the Doxyfile  
   - At `doxyguard_db/doxygen.py:583`, excludes become `EXCLUDE =` (cleared then re-applied)

5. **Logging:**
   - `doxyguard_db/scope.py:728` logs at WARNING level that the whole repository is being indexed, with a reason clause that names where a declaration could have been placed

## Gaps

None. The code traces completely from the CLI entry point through to the doxygen invocation with clear file citations at each step.
