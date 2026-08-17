# Q6 — mcp — haiku — run 1

Perfect. Now I have all the necessary information to answer comprehensively. Let me compile the answer:

---

## Answer

When a colleague mistypes a key in a YAML manifest, the behavior depends on which level the key appears and what kind of mistake it is. Here's the complete flow at every level:

### **LEVEL 1: Invalid YAML Syntax (unparseable file)**

Example: `shared_key_patterns: [oops` (unclosed bracket)

**What happens:**
1. `_read_mapping` in declaration.py:347-351 calls `yaml.safe_load()`
2. Catches `yaml.YAMLError` exception
3. Logs a **WARNING** (declaration.py:353): `"%s is unreadable (%s) — ignoring it, using defaults"`
4. Returns `{}` (empty dict)
5. **Result: Build proceeds with defaults, no error**

**Test evidence:** `test_malformed_declaration_degrades_to_defaults` in test_declaration.py:41-48

---

### **LEVEL 2: Valid YAML, Wrong Document-Level Section Name**

Example in `.doxyguard-db.yaml`:
```yaml
preprocessors:          # typo: should be "preprocessor"
  predefined:
    - SOME_MACRO
```

**What happens:**
1. File parses successfully as YAML
2. `load_declaration_located` in declaration.py:330 gets the parsed dict
3. Compares each key against `KNOWN_SECTIONS` frozenset (declaration.py:234-241)
4. Unknown key found: `preprocessors` not in allowed list
5. **RAISES `DeclarationError`** (declaration.py:330-336) with message:
   ```
   ".doxyguard-db.yaml: unknown section(s) 'preprocessors' 
    — allowed: ..., 'preprocessor', ..."
   ```
6. **Result: Build FAILS immediately**

**Test evidence:** `test_a_misspelled_section_is_refused` in test_preprocessor.py:686-702 and `test_an_unknown_section_is_refused` in test_declaration.py:173-180

---

### **LEVEL 3: Valid YAML, Valid Section Name, Wrong Entry-Level Key**

This applies within declared entries (like dispatch, threads, shared_key_patterns, etc).

Example in `dispatch:` section:
```yaml
dispatch:
  shared_key_wrappers:
    - pattern: store_bool
      key_arg_idx: 2        # typo: should be "key_arg_index"
```

**What happens:**
1. Section parses successfully, entry dict is created
2. `_wrapper_entry` in dispatch.py:367-381 is called
3. Line 375: `_reject_unknown(entry, _WRAPPER_KEYS, ...)` where `_WRAPPER_KEYS = {"pattern", "key_arg_index", "direction"}` (dispatch.py:99)
4. `_reject_unknown` at dispatch.py:116 builds `unknown` list of keys not in allowed set
5. **RAISES `DeclarationError`** (dispatch.py:118-121) with message:
   ```
   ".doxyguard-db.yaml [dispatch]: .../shared_key_wrappers entry: 
    unknown key(s) 'key_arg_idx' — allowed: 'direction', 'key_arg_index', 'pattern'"
   ```
6. **Result: Build FAILS immediately**

**Why this matters (from dispatch.py:91-95):** Without this check, `key_arg_idx` would silently default to argument 0 (line 381), producing **wrong dataflow from a typo** — a build that succeeds while encoding a completely different data model than intended.

**Test evidence:** `test_a_misspelled_entry_field_refuses_the_build` in test_dispatch.py:770-783. Line 775 shows exactly this typo: `key_arg_idx` is rejected with both the typo and the correct spelling named.

---

### **LEVEL 3B: Valid YAML, Valid Section, Wrong Entry Shape**

Example:
```yaml
shared_key_wrappers:
  pattern: store_bool       # wrong: should be a LIST of dicts
  key_arg_index: 0
```

**What happens:**
1. `_entries` in dispatch.py:305-310 retrieves the section value
2. Checks `isinstance(raw, list)` and `all(isinstance(e, dict) for e in raw)` (line 308)
3. **RAISES `DeclarationError`** (line 309): `"...: shared_key_wrappers must be a list of mappings"`
4. **Result: Build FAILS immediately**

**Test evidence:** `test_a_section_that_is_not_a_list_of_mappings_refuses_the_build` in test_dispatch.py:813-819

---

### **LEVEL 4: Value-Level Validation**

Example:
```yaml
shared_key_wrappers:
  - pattern: store
    direction: wrtie         # typo: should be "write" or "read"
```

**What happens:**
1. `_wrapper_entry` calls `KEY_DIRECTION.validated()` at dispatch.py:378-380
2. Validates the enum value against the vocabulary
3. **RAISES `DeclarationError`** naming the origin, token, and allowed set
4. **Result: Build FAILS immediately**

**Test evidence:** `test_a_typod_direction_refuses_instead_of_filing_the_opposite_role` in test_dispatch.py:801-810

---

### **Correctly Written Manifest**

```yaml
dispatch:
  shared_key_wrappers:
    - pattern: store_bool_on_delta
      key_arg_index: 0
      direction: write
```

**What happens:**
1. `_document` successfully parses to dict
2. `_reject_unknown` at document level passes (all keys are in `_DOCUMENT_KEYS`)
3. `_entries` successfully extracts the list
4. `_wrapper_entry` successfully validates:
   - `_reject_unknown` passes (all keys are in `_WRAPPER_KEYS`)
   - `pattern` required field is present
   - `direction` enum value is valid (line 378-380 validates against allowed values)
5. `_declared_keys_from_doc` builds the manifest
6. **Result: Build succeeds, dataflow edges are recorded**

**Test evidence:** `test_declared_key_wrapper_produces_the_dataflow_edge` in test_dispatch.py:868

---

### **Invalid YAML vs. Misspelled Keys: The Key Difference**

| Scenario | Example | Handling | Result |
|----------|---------|----------|--------|
| **Invalid YAML syntax** | `[unclosed` | `_read_mapping` catches `yaml.YAMLError` | WARNING logged, degraded to defaults, **build succeeds** |
| **Valid YAML, wrong section name** | `preprocessors:` instead of `preprocessor` | `_reject_unknown` at document level | **Build FAILS with DeclarationError** |
| **Valid YAML, wrong entry key** | `key_arg_idx` instead of `key_arg_index` | `_reject_unknown` at entry level | **Build FAILS with DeclarationError** |
| **Valid YAML, wrong entry shape** | Dict instead of list of dicts | `_entries` type check | **Build FAILS with DeclarationError** |

**The deliberate design (from dispatch.py:414-420):** Anything malformed **RAISES** rather than degrading, because "a silently-ignored declaration is indistinguishable from never having written one." A misspelled section or key is a document that parses where the author plainly intended something, so degrading would mean running on built-in defaults while falsely reporting that the declaration was honoured — worse than refusing.

---

## Gaps

None. Every level of key validation is instrumented with explicit tests and the code paths are direct and traceable.
