# Q6 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll explore the codebase to understand how it reads and validates YAML manifests, particularly how it handles misspelled keys.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "*.py" | head -20
- **got:** ~/ddb-targets/self/acceptance/bench/rescore_audit.py ~/ddb-targets/self/acceptance/bench/fallback_audit.py ~/ddb-targets/self/acceptance/bench/arm_headroom.py ~/ddb-targets/self/acceptance/bench/bench_arms.py ~/ddb-targe…

### 2. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "*.yaml" -o -name "*.yml" | head -20
- **got:** ~/ddb-targets/self/acceptance/targets/entropic/questions.yaml ~/ddb-targets/self/acceptance/targets/self/questions.yaml ~/ddb-targets/self/acceptance/targets/mbedtls/questions.yaml ~/ddb-targets/self/acceptance/targets/m…

### 3. `Bash`
- **asked:** command=grep -r "yaml\|YAML" ~/ddb-targets/self --include="*.py" | grep -E "load|read|parse" | head -20
- **got:** ~/ddb-targets/self/acceptance/bench/rubric_fix.py:    entry = yaml.safe_load("".join(ln[4:] for ln in old))[0] ~/ddb-targets/self/acceptance/bench/rubric_fix.py:    before = bench_rubric.parse_rubric_yaml(args.rubric) ~/…

### 4. `Bash`
- **asked:** command=grep -r "doxygen.guard\|doxygen-guard" ~/ddb-targets/self --include="*.py" | grep -E "\.yaml|load|parse" | head -20
- **got:** ~/ddb-targets/self/doxyguard_db/requirements.py:     (id/name columns via the repo's DECLARED `.doxygen-guard.yaml` ~/ddb-targets/self/doxyguard_db/requirements.py:     (`.doxygen-guard.yaml` `validate.tags.req.pattern`)…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/declaration.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""A target repo's own `.doxyguard-db.yaml` — its declared indexing conventions. 3	 4	doxyguard-db's central mandate is built-in defaults plus a DECLARED override, never a 5	hardcoded a…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""The indirect-dispatch DECLARATION — a repo's own map of its indirections. 3	 4	The static graph recovers a relationship only when both endpoints are named at 5	the site. A call edge …

### 7. `Bash`
- **asked:** command=grep -n "_reject_unknown\|def load_dispatch" ~/ddb-targets/self/doxyguard_db/dispatch.py | head -20
- **got:** 109:def _reject_unknown(mapping: dict, allowed: frozenset[str], owner: str) -> None: 327:    _reject_unknown(entry, _INTERFACE_KEYS, f"{origin}: {KEY_INTERFACES} entry") 354:    _reject_unknown(entry, _TABLE_KEYS, f"{ori…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 414	def load_dispatch_manifest(source: Path | dict | None) -> DispatchManifest: 415	    """Undeclared is the norm: no repo has written a dispatch declaration yet, so 416	    this returns an empty manifest and the pipelin…

### 9. `Bash`
- **asked:** command=grep -n "def _document" ~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 389:def _document(source: Path | dict | None) -> dict | None:

### 10. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 389	def _document(source: Path | dict | None) -> dict | None: 390	    """Both delivery routes converge here, so a standalone `--dispatch` file and 391	    the `.doxyguard-db.yaml` section are guaranteed to have exactly o…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/dispatch.py
- **got:** 360	 361	## @brief Parse one `shared_key_wrappers:` entry. 362	## @param entry The entry mapping. 363	## @param origin Where it was declared. 364	## @return The validated KeyWrapper. 365	## @version 1 366	## @dg_internal…

### 12. `Bash`
- **asked:** command=find ~/ddb-targets/self -name "test_declaration.py" -o -name "test_dispatch.py" | head -5
- **got:** ~/ddb-targets/self/tests/test_declaration.py ~/ddb-targets/self/tests/test_dispatch.py

### 13. `Bash`
- **asked:** command=grep -n "misspell\|unknown\|singular\|plural" ~/ddb-targets/self/tests/test_declaration.py
- **got:** 170:# ─── a misspelled section is refused, not silently defaulted ───────────────── 173:def test_an_unknown_section_is_refused(tmp_path: Path) -> None: 176:    A singular/plural slip parses to valid YAML that NO consumer…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_declaration.py
- **got:** 170	# ─── a misspelled section is refused, not silently defaulted ───────────────── 171	 172	 173	def test_an_unknown_section_is_refused(tmp_path: Path) -> None: 174	    """The no-hardcoding mandate's worst case, closed …

### 15. `Bash`
- **asked:** command=grep -n "YAMLError\|malformed\|invalid" ~/ddb-targets/self/tests/test_declaration.py | head -20
- **got:** 41:def test_malformed_declaration_degrades_to_defaults(tmp_path: Path) -> None: 100:    assert manifest_key(a) != manifest_key(b), "a changed declaration must invalidate" 158:def test_string_list_section_ignores_a_malfor…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_declaration.py
- **got:** 41	def test_malformed_declaration_degrades_to_defaults(tmp_path: Path) -> None: 42	    """A typo must not fail a build that would otherwise succeed — it warns and 43	    falls back, rather than taking the repo's index do…

### 17. `Bash`
- **asked:** command=grep -n "unknown\|misspell\|singular" ~/ddb-targets/self/tests/test_dispatch.py | head -20
- **got:** 514:    edge for that registration. That is the correct answer to "which one" being unknown, and the 533:        "two same-named handlers means the target is unknown; one registration must not " 716:    mechanism strips …

### 18. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_dispatch.py
- **got:** 756	def test_a_misspelled_section_refuses_the_build(tmp_path: Path) -> None: 757	    """The hole in the fail-closed promise, closed. An ABSENT section reads as 758	    "declared nothing", so every plausible singular/plur…

### 19. `Bash`
- **asked:** command=cd ~/ddb-targets/self && python3 -c " import yaml # Test 1: Invalid YAML try:     yaml.safe_load('shared_key_patterns: [oops') except yaml.YAMLError as e:     print('Test 1 - Invalid YAML syntax:')     print(f'  Exception type: {type(e).__name__}')     print(f'  Error: {str(e)[:80]}')  # Test 2: Valid YAML but not a mapping try:     result = yaml.safe_load('- not\n- a\n- mapping')     print(f'\nTest 2 - Valid YAML list (not mapping):')     print(f'  Result type: {type(result).__name__}')     print(f'  Result: {result}') except yaml.YAMLError as e:     print(f'  Exception: {e}')  # Test 3: Valid YAML mapping with unknown key try:     result = yaml.safe_load('shared_key_pattern:\n  - prefix: Store_Set')     print(f'\nTest 3 - Valid YAML with misspelled key:')     print(f'  Result: {result}')     print(f'  Key exists: {\"shared_key_pattern\" in result}') except yaml.YAMLError as e:     print(f'  Exception: {e}') " 
- **got:** Test 1 - Invalid YAML syntax:   Exception type: ParserError   Error: while parsing a flow sequence   in "<unicode string>", line 1, column 22:     sh  Test 2 - Valid YAML list (not mapping):   Result type: list   Result:…

**Reasoning.** Perfect. Now I have the complete picture. Let me trace through exactly what happens at every level when a key is misspelled.

## ANSWER

The program reads YAML manifests (`.doxyguard-db.yaml` and related declarations) at **three distinct levels**, each with its own validation. A misspelled key behaves differently at each level.

### Level 1: Document-level sections (top-level keys)

**Correctly spelled section** (e.g., `shared_key_patterns`):
1. File is read via `yaml.safe_load()` → produces a valid Python dict
2. `load_declaration_located()` checks if each key is in `KNOWN_SECTIONS` (`declara

---

## Final answer as submitted

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
