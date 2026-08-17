# Q6 — src — haiku — run 1

Perfect. Now I have the complete picture. Let me trace through exactly what happens at every level when a key is misspelled.

## ANSWER

The program reads YAML manifests (`.doxyguard-db.yaml` and related declarations) at **three distinct levels**, each with its own validation. A misspelled key behaves differently at each level.

### Level 1: Document-level sections (top-level keys)

**Correctly spelled section** (e.g., `shared_key_patterns`):
1. File is read via `yaml.safe_load()` → produces a valid Python dict
2. `load_declaration_located()` checks if each key is in `KNOWN_SECTIONS` (`declaration.py:328`)
3. Key matches → continues; section is processed by its consumer

**Misspelled section** (e.g., `shared_key_pattern` — singular instead of plural):
1. File is read via `yaml.safe_load()` → produces a valid Python dict (misspelling is just another key)
2. `load_declaration_located()` at line 328-335 checks: `unknown = sorted(str(key) for key in data if key not in KNOWN_SECTIONS)`
3. **Raises `DeclarationError`** with message: `"unknown section(s) 'shared_key_pattern' — allowed: 'shared_key_patterns', ..."`
4. Build fails immediately; manifest is not honored

The test confirming this is `test_declaration.py:173-198`, which shows both `shared_key_pattern` and `thread_pattern` (singular) are caught and refused.

### Level 2: Entry-level keys (keys within nested structures)

At this level, misspellings are even MORE dangerous because they used to fail silently. The code now validates with `_reject_unknown()` (`dispatch.py:109-121`).

**For dispatch manifest `dispatch.py`:**

**Correctly spelled entry key** (e.g., `key_arg_index`):
1. Parsed as part of a `shared_key_wrappers` entry mapping
2. `_wrapper_entry()` at line 375 calls: `_reject_unknown(entry, _WRAPPER_KEYS, origin)`
3. `_WRAPPER_KEYS = frozenset({"pattern", "key_arg_index", "direction"})` at line 99
4. Key matches → accepted; value is read and used

**Misspelled entry key** (e.g., `key_arg_idx` for `key_arg_index`):
1. Parsed into the entry mapping alongside correct keys
2. `_reject_unknown()` detects `"key_arg_idx"` ∉ `_WRAPPER_KEYS`
3. **Raises `DeclarationError`**: `"unknown key(s) 'key_arg_idx' — allowed: 'key_arg_index', 'direction', 'pattern'"`
4. Build fails
5. **Without this check**, the code would have silently used the default value (line 93-95 explain the hole: "`key_arg_idx` silently defaults the key to argument 0, which does not produce 'no dataflow' but the WRONG dataflow"`)

The tests confirming this are:
- `test_dispatch.py:756-767`: Misspelled sections at document level (`interface`, `dispatch_table`, `shared_key_wrapper`)
- `test_dispatch.py:770-783`: Misspelled entry fields (`key_arg_idx`, `bind`, `handler`)

### Level 3: Invalid YAML syntax vs. misspelled keys

**Invalid YAML** (e.g., `shared_key_patterns: [oops` — unclosed bracket):
1. `yaml.safe_load()` at `declaration.py:350` raises `yaml.YAMLError` (type: `ParserError`)
2. Exception is caught at line 351
3. Logs **warning**: `"%s is unreadable (%s) — ignoring it, using defaults"`
4. **Returns `{}`** (empty dict)
5. Build proceeds with **built-in defaults**
6. No error; degradation is silent

**Non-mapping YAML** (e.g., list instead of dict: `- not\n- a\n- mapping`):
1. `yaml.safe_load()` succeeds → returns `["not", "a", "mapping"]`
2. `isinstance(data, dict)` check fails at `declaration.py:354`
3. Logs **warning**: `"%s does not contain a mapping — ignoring it, using defaults"`
4. **Returns `{}`**
5. Build proceeds with **built-in defaults**
6. No error; degradation is silent

This is tested at `test_declaration.py:41-48`.

---

### Difference: Misspelled key vs. invalid YAML

| Case | Result | Behavior |
|---|---|---|
| **Correctly spelled key** | Key found in allowed set | Section is read and applied |
| **Misspelled key** (known sections) | `DeclarationError` raised | Build **fails immediately** with helpful message naming allowed spellings |
| **Misspelled key** (entry level) | `DeclarationError` raised | Build **fails immediately** with helpful message naming allowed fields |
| **Invalid YAML syntax** | `yaml.YAMLError` caught | Logs warning; **degrades to built-in defaults** (no error) |
| **Non-mapping YAML** | `isinstance` check fails | Logs warning; **degrades to built-in defaults** (no error) |

**The critical design choice:** Misspelled section and entry keys are **REFUSED** (fail-closed), while malformed YAML is **DEGRADED** (silent fallback). This is deliberate: a misspelling indicates intent (the author wrote something that parses), while malformed syntax indicates an accident. The `declaration.py:295-301` comment explains: "A misspelled section is a document that parses, where the author plainly intended something — and degrading there means running on built-in defaults **while reporting that the declaration was read**. So this REFUSES."

---

## Gaps

No gaps found. The code paths, test coverage, and error-handling strategy are completely documented and verified through source and tests.
