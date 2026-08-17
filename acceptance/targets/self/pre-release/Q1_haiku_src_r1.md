# Q1 — src — haiku — run 1

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
