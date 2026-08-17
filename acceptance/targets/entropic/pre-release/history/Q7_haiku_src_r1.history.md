# Q7 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll explore the repository structure to understand where this function would belong and how it would be integrated.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/entropic -type f -name "*.cpp" -o -name "*.h" | head -20
- **got:** ~/ddb-targets/entropic/src/facade/entropic_compaction.cpp ~/ddb-targets/entropic/src/facade/entropic_mcp.cpp ~/ddb-targets/entropic/src/facade/engine_handle.h ~/ddb-targets/entropic/src/facade/entropic_audit.cpp ~/ddb-ta…

### 2. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file entropic.cpp 4	 * @brief librentropic facade — C API implementation. 5	 * 6	 * Owns the EntropicEngine handle struct and implements lifecycle 7	 * (create/configu…

**Reasoning.** Now let me check the header file to understand the public API structure:

### 3. `Bash`
- **asked:** command=find ~/ddb-targets/entropic -name "entropic.h" -type f
- **got:** ~/ddb-targets/entropic/include/entropic/entropic.h

### 4. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/entropic.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file entropic.h 4	 * @brief Public C API for the Entropic inference engine. 5	 * 6	 * This is the unified facade. Most consumers link against librentropic 7	 * and inc…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 1877	void entropic_destroy(entropic_handle_t handle) { 1878	    if (handle == nullptr) { 1879	        return; 1880	    } 1881	    s_log->info("entropic_destroy()"); 1882	 1883	    // Stop external bridge FIRST — it holds…

### 6. `Bash`
- **asked:** command=tail -100 ~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** *         ENTROPIC_ERROR_INVALID_STATE.  * @internal  * @version 2.1.11  */ entropic_error_t entropic_speculative_compat(     entropic_handle_t handle,     int* compatible,     char** diagnostic) {     if (handle == null…

### 7. `Bash`
- **asked:** command=grep -n "entropic_acceptance" ~/ddb-targets/entropic/include/entropic/entropic.h
- **got:** (Bash completed with no output)

### 8. `Bash`
- **asked:** command=grep "ENTROPIC_EXPORT" ~/ddb-targets/entropic/include/entropic/entropic.h | head -5
- **got:** ENTROPIC_EXPORT entropic_error_t entropic_create(entropic_handle_t* handle); ENTROPIC_EXPORT entropic_error_t entropic_configure( ENTROPIC_EXPORT entropic_error_t entropic_configure_from_file( ENTROPIC_EXPORT entropic_er…

### 9. `Bash`
- **asked:** command=grep -E "int\s+entropic_[a-z_]+\s*\(\s*void\s*\)" ~/ddb-targets/entropic/include/entropic/entropic.h
- **got:** ENTROPIC_EXPORT int entropic_api_version(void);

### 10. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/entropic.h
- **got:** 100	 101	/** 102	 * @brief Configure engine from a YAML or JSON config file. 103	 * 104	 * Convenience wrapper that reads the file, parses it (YAML via ryml or 105	 * JSON via nlohmann/json based on extension), and appli…

### 11. `Bash`
- **asked:** command=find ~/ddb-targets/entropic -name "*export*" -type f | head -5
- **got:** ~/ddb-targets/entropic/extern/llama.cpp/tests/test-export-graph-ops.cpp ~/ddb-targets/entropic/extern/llama.cpp/tools/export-lora/export-lora.cpp ~/ddb-targets/entropic/extern/llama.cpp/tools/ui/src/lib/constants/message…

### 12. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/entropic_export.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file entropic_export.h 4	 * @brief Symbol visibility macro for all exported symbols. 5	 * 6	 * Applied ONLY to: 7	 * - Factory functions (entropic_create_server, entro…

**Reasoning.** Now let me verify the linkage model by checking the CMake visibility settings:

### 13. `Bash`
- **asked:** command=grep -r "CMAKE_CXX_VISIBILITY" ~/ddb-targets/entropic 2>/dev/null | head -3
- **got:** ~/ddb-targets/entropic/.claude/proposals/STAGED/v1.8.0-cpp-scaffold.md:set(CMAKE_CXX_VISIBILITY_PRESET hidden) ~/ddb-targets/entropic/.claude/proposals/STAGED/v1.8.0-cpp-scaffold.md: * All other symbols are hidden by def…

**Reasoning.** ## Answer

I cannot add the function directly (as the constraint specifies "Do not write files"), but I can describe exactly what it would look like based on the codebase patterns I've read.

### Function Specification

**Signature:**
```c
int entropic_acceptance_probe(void);
```
`src/facade/entropic.cpp:line-TBD` (would be within the `extern "C"` block)

**File location:** `src/facade/entropic.cpp:228-4124` (the `extern "C"` block spans these lines `src/facade/entropic.cpp:228`)

**Doxygen comment (required by the codebase):**
Based on the pattern seen at `src/facade/entropic.cpp:1908-1915` (

---

## Final answer as submitted

## Answer

I cannot add the function directly (as the constraint specifies "Do not write files"), but I can describe exactly what it would look like based on the codebase patterns I've read.

### Function Specification

**Signature:**
```c
int entropic_acceptance_probe(void);
```
`src/facade/entropic.cpp:line-TBD` (would be within the `extern "C"` block)

**File location:** `src/facade/entropic.cpp:228-4124` (the `extern "C"` block spans these lines `src/facade/entropic.cpp:228`)

**Doxygen comment (required by the codebase):**
Based on the pattern seen at `src/facade/entropic.cpp:1908-1915` (the `entropic_version` function pattern), it would be:

```cpp
/**
 * @brief Acceptance-test probe — returns readiness status for acceptance testing.
 * @return Integer status code indicating readiness.
 * @utility
 * @version X.Y.Z
 */
```

Following the pattern of similar functions like `entropic_api_version()` at `src/facade/entropic.cpp:1923-1925`.

**Does anything call it:** No. It's a newly-added function with no existing call sites.

**Visibility to consumers linking against librentropic:**

**Would NOT be visible by default.** Because:

1. The codebase uses `CMAKE_CXX_VISIBILITY_PRESET=hidden` (`entropic_export.h:11`)
2. All symbols are hidden unless marked with `ENTROPIC_EXPORT`
3. If `entropic_acceptance_probe` is added to `src/facade/entropic.cpp` **without** a corresponding declaration in `include/entropic/entropic.h` marked with `ENTROPIC_EXPORT`, it would be a private symbol (`__attribute__((visibility("default")))` on non-Windows, per `entropic_export.h:28`)

To make it visible to a consumer:
- Must declare it in `include/entropic/entropic.h` with `ENTROPIC_EXPORT` prefix (pattern seen at `entropic.h:196`)
- Must implement it in `src/facade/entropic.cpp` within the `extern "C"` block (pattern at `src/facade/entropic.cpp:228`)

## Gaps

- Cannot verify the exact line number it would occupy without writing the file
- Cannot confirm its implementation body (the specification only defines signature, documentation, and visibility)
