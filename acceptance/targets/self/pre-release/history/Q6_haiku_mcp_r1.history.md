# Q6 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":8,"results":[{"name":"_parse_data_model_yaml","kind":"function","file":"doxyguard_db/shared_key_edges.py","brief":"Parse a YAML data-model manifest into declared-key entries."},{"name":…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"doxyguard_db/buildoptions.py","kind":"file","file":"doxyguard_db/buildoptions.py","brief":"TIER 1, REACHABLE — one structured `options` argument for an embedding c…

### 3. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"kind":"dossiers","count":3,"found":2,"subject":["load_declaration","load_config","_parse_data_model_yaml"],"results":[{"subject":"load_declaration","subject_kind":"function","name":"load_declaration","rowid":1813,"sign…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject
- **got:** {"subject":"load_declaration_located","subject_kind":"function","name":"load_declaration_located","rowid":1814,"signature":" tuple[dict[str, Any], Path | None] doxyguard_db.declaration.load_declaration_located(Path|str|N…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["_read_mapping","KNOWN_SECTIONS"],"results":[{"subject":"_read_mapping","subject_kind":"function","name":"_read_mapping","rowid":1816,"signature":" dict[str, Any] doxygua…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"test_a_misspelled_section_is_refused","subject_kind":"function","name":"test_a_misspelled_section_is_refused","rowid":4569,"signature":" None test_preprocessor.test_a_misspelled_section_is_refused(Path tmp_pa…

### 7. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"reject_unknown entry key","note":"No matching symbols for 'reject_unknown entry key'. This is NOT an error and NOT a malformed call, and it is NOT a definitive…

### 8. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"doxyguard_db/mcp_server/descriptions.py","kind":"file","file":"doxyguard_db/mcp_server/descriptions.py","brief":"Loader for the MCP tool descriptions, which live i…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""The indirect-dispatch DECLARATION — a repo's own map of its indirections. 3	 4	The static graph recovers a relationship only when both endpoints are named at 5	the site. A call edge …

### 10. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"_reject_unknown","subject_kind":"function","name":"_reject_unknown","rowid":1836,"signature":" None doxyguard_db.dispatch._reject_unknown(dict mapping, frozenset[str] allowed, str owner)","file":"doxyguard_db…

### 11. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject
- **got:** {"kind":"dossiers","count":4,"found":4,"subject":["load_dispatch_manifest","_interface_entry","_table_entry","_wrapper_entry"],"results":[{"subject":"load_dispatch_manifest","subject_kind":"function","name":"load_dispatc…

### 12. `Grep`
- **asked:** pattern=test_a_misspelled_section_refuses_the_build|test_a_misspelled_entry_field_refuses_the_build|test_a_manifest_file_that_is_not_a_mapping_refuses_the_build
- **got:** No matches found

### 13. `Grep`
- **asked:** pattern=test_a_misspelled
- **got:** No files found

### 14. `bash`
- **asked:** command=cd ~/ddb-targets/self && find . -name "*.py" -path "*/tests/*" -exec grep -l "misspelled" {} \;
- **got ⚠ error:** <tool_use_error>Error: No such tool available: bash</tool_use_error>

### 15. `Grep`
- **asked:** pattern=misspelled, path=~/ddb-targets/self/tests
- **got:** Found 7 files ~/ddb-targets/self/tests/test_subject_surface.py ~/ddb-targets/self/tests/test_preprocessor.py ~/ddb-targets/self/tests/test_mcp_server.py ~/ddb-targets/self/tests/test_declaration.py ~/ddb-targets/self/tes…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Layer 6: the declared indirect-dispatch recovery (tasks #60 / #30 / #35 / #37). 3	 4	Three indirections hide one endpoint of a relationship, so the static graph 5	cannot see it: a vi…

### 17. `Grep`
- **asked:** pattern=def test_a_misspelled_entry_field, path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** 750-    assert _declared_edges(db) == [] 751-    # Not even the terminus table is created: the stage returns before touching 752-    # the database at all. 753-    assert _boundaries(db) == [] 754- 755- 756-def test_a_mi…

### 18. `Grep`
- **asked:** pattern=def test_a_manifest_file_that_is_not_a_mapping, path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** 870-    assert [b.interface for b in from_flag.interfaces] == ["FromFlag"] 871- 872-    # A repo declaring nothing reaches the stage with an empty manifest, not None. 873-    assert load_dispatch_manifest(_declared_or_fl…

### 19. `Grep`
- **asked:** pattern=def test_a_section_that_is_not_a_list_of_mappings, path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** 793-    with pytest.raises(DeclarationError, match="would do nothing"): 794-        load_dispatch_manifest({"interfaces": [{"interface": "I"}]}) 795-    with pytest.raises(DeclarationError, match="dispatch_via"): 796-   …

### 20. `Grep`
- **asked:** pattern=malformed|YAMLError, path=~/ddb-targets/self/tests/test_declaration.py
- **got:** 26-    load_declaration, 27-    section, 28-) 29-from doxyguard_db.shared_key_edges import load_shared_key_patterns 30-from doxyguard_db.threads import DEFAULT_SPAWN_PATTERNS, load_thread_patterns 31-from doxyguard_db.tr…

### 21. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 300	    author with a green build and the gap they were closing still open. 301	 302	    @brief Read one section as a list of entry mappings. 303	    @version 1 304	    """ 305	    raw = doc.get(name) 306	    if raw is N…

### 22. `Grep`
- **asked:** pattern=^def _document, path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 369-    opposite role inverts the dataflow the entry exists to reveal, and would 370-    still build green. 371- 372-    @brief Validate one declared argument-keyed wrapper. 373-    @version 2 374-    """ 375-    _reject…

### 23. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_declaration.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""A target repo's `.doxyguard-db.yaml` declaration (task #51). 3	 4	Every convention override was a CLI flag, and the MCP server passes none of them 5	— so through the MCP server, the …

**Reasoning.** Now let me look at the critical test that shows what happens:

### 24. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** 890	def test_a_manifest_file_that_is_not_a_mapping_refuses_the_build(tmp_path: Path) -> None: 891	    """@brief A YAML list (or scalar) where a mapping belongs is refused.""" 892	    path = tmp_path / "dispatch.yaml" 893…

### 25. `Grep`
- **asked:** pattern=yaml.YAMLError|safe_load, path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** No files found

### 26. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 389	def _document(source: Path | dict | None) -> dict | None: 390	    """Both delivery routes converge here, so a standalone `--dispatch` file and 391	    the `.doxyguard-db.yaml` section are guaranteed to have exactly o…

**Reasoning.** Perfect. Now I have all the necessary information to answer comprehensively. Let me compile the answer:

---

## Answer

When a colleague mistypes a key in a YAML manifest, the behavior depends on which level the key appears and what kind of mistake it is. Here's the complete flow at every level:

### **LEVEL 1: Invalid YAML Syntax (unparseable file)**

Example: `shared_key_patterns: [oops` (unclosed bracket)

**What happens:**
1. `_read_mapping` in declaration.py:347-351 calls `yaml.safe_load()`
2. Catches `yaml.YAMLError` exception
3. Logs a **WARNING** (declaration.py:353): `"%s is unreadab

---

## Final answer as submitted

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
