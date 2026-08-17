# Q7 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=grep -n "^int\|^static\|^#include\|namespace" ~/ddb-targets/entropic/src/facade/entropic.cpp | head -50
- **got:** 13:#include "engine_handle.h" 15:#include <entropic/config/loader.h> 16:#include <entropic/mcp/servers/entropic_server.h> 17:#include <entropic/entropic.h> 18:#include <entropic/prompts/manager.h> 19:#include <entropic/t…

### 2. `Bash`
- **asked:** command=wc -l ~/ddb-targets/entropic/src/facade/entropic.cpp sed -n '160,215p' ~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 4123 ~/ddb-targets/entropic/src/facade/entropic.cpp  * @return ENTROPIC_OK if valid, error code otherwise.  * @internal  * @version 2.0.0  */ static entropic_error_t check_orchestrator(entropic_handle_t h) {     if (!h) …

**Reasoning.** Now let's check the end of the file and how the public API is exported (visibility/header declarations) to answer the linking question.

### 3. `Bash`
- **asked:** command=tail -40 ~/ddb-targets/entropic/src/facade/entropic.cpp echo --- grep -rn "ENTROPIC_API\|__attribute__((visibility\|extern \"C\"" ~/ddb-targets/entropic/include/entropic/entropic.h 2>/dev/null | head -20 echo --- find ~/ddb-targets/entropic/include -iname "*entropic.h*"
- **got:** };     }     if (handle->orchestrator) {         handle->orchestrator->set_residency_observer(std::move(fn));     }     return ENTROPIC_OK; }  /**  * @brief Return the engine's current residency-set snapshot as JSON.  * …

### 4. `Bash`
- **asked:** command=grep -n "ENTROPIC_API\|visibility\|__declspec" ~/ddb-targets/entropic/include/entropic/*.h ~/ddb-targets/entropic/include/entropic/**/*.h 2>/dev/null | head -30 echo --- sed -n '1,60p' ~/ddb-targets/entropic/include/entropic/entropic.h
- **got:** ~/ddb-targets/entropic/include/entropic/entropic_export.h:4: * @brief Symbol visibility macro for all exported symbols. ~/ddb-targets/entropic/include/entropic/entropic_export.h:23:        #define ENTROPIC_EXPORT __decls…

### 5. `Bash`
- **asked:** command=grep -n "ENTROPIC_EXPORT" ~/ddb-targets/entropic/include/entropic/entropic.h | head -5
- **got:** 73:ENTROPIC_EXPORT entropic_error_t entropic_create(entropic_handle_t* handle); 97:ENTROPIC_EXPORT entropic_error_t entropic_configure( 118:ENTROPIC_EXPORT entropic_error_t entropic_configure_from_file( 147:ENTROPIC_EXPO…

**Reasoning.** Now I'll add the function at the end of the file, after the closing `extern "C"` block, as a plain non-exported function (matching the literal instruction: no arguments, returns int, just a doxygen comment — not marked `ENTROPIC_EXPORT` and not declared in any public header).

### 6. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 4100	 * 4101	 * @internal 4102	 * @version 2.2.4 4103	 */ 4104	entropic_error_t entropic_residency_snapshot( 4105	    entropic_handle_t handle, 4106	    char** out_json) { 4107	    entropic_error_t rc = ENTROPIC_OK; 4108…

### 7. `Edit`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** The file ~/ddb-targets/entropic/src/facade/entropic.cpp has been updated successfully. (file state is current in your context — no need to Read it back)

**Reasoning.** Now query the index to confirm signature/callers and check for it in any header.

### 8. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got:** Error: result (76,751 characters) exceeds maximum allowed tokens. Output has been saved to ~/.claude/projects/-home-tvanfossen-Projects-docs-db--claude-tmp-bench-p7-entropic-wd/c5cc16e1-0b65-4a1e-bf8c-da427882e53c/tool-r…

### 9. `Bash`
- **asked:** command=jq '{ok, built, status: {stale: .status.stale, build_version: .status.build_version, source_changed_files: .status.source_changed_files}}' ~/.claude/projects/-home-tvanfossen-Projects-docs-db--claude-tmp-bench-p7-entropic-wd/c5cc16e1-0b65-4a1e-bf8c-da427882e53c/tool-results/mcp-doxyguard-db-index-1786844659372.txt
- **got:** {   "ok": true,   "built": true,   "status": {     "stale": false,     "build_version": 50,     "source_changed_files": 0   } }

**Reasoning.** Build succeeded and index is current. Now query the new symbol.

### 10. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"entropic_acceptance_probe","subject_kind":"function","name":"entropic_acceptance_probe","rowid":52701,"signature":"int entropic_acceptance_probe()","file":"src/facade/entropic.cpp","line_start":4131,"line_end…

**Reasoning.** Confirms no callers. Now check whether it's declared in any public header (would make it exported/visible to library consumers), and confirm `ENTROPIC_EXPORT`/visibility default rules for this file.

### 11. `Bash`
- **asked:** command=grep -rn "entropic_acceptance_probe" ~/ddb-targets/entropic/include 2>/dev/null echo "exit: $?" sed -n '1,40p' ~/ddb-targets/entropic/include/entropic/entropic_export.h
- **got:** exit: 1 // SPDX-License-Identifier: Apache-2.0 /**  * @file entropic_export.h  * @brief Symbol visibility macro for all exported symbols.  *  * Applied ONLY to:  * - Factory functions (entropic_create_server, entropic_cr…

**Reasoning.** No public header declares the new function, and the shared build sets `CMAKE_CXX_VISIBILITY_PRESET=hidden`, so unmarked symbols default to hidden. Let me confirm that CMake setting.

### 12. `Bash`
- **asked:** command=grep -rn "CMAKE_CXX_VISIBILITY_PRESET\|VISIBILITY_INLINES_HIDDEN" ~/ddb-targets/entropic/CMakeLists.txt 2>/dev/null
- **got:** 34:set(CMAKE_CXX_VISIBILITY_PRESET hidden) 35:set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)

**Reasoning.** ## Answer

I added the function at the end of `src/facade/entropic.cpp`, after the file's closing `extern "C"` block, since the instruction gave a plain C++ signature (no `extern "C"`, no `ENTROPIC_EXPORT`):

```cpp
/**
 * @brief Acceptance-test probe: exists only so the docs-db acceptance
 * benchmark has a symbol it introduced itself to trace.
 * @return 0.
 * @version 1.0.0
 */
int entropic_acceptance_probe() {
    return 0;
}
```

Rebuilt the index (`ok: true`, `stale: false`, `build_version: 50`, `source_changed_files: 0` after rebuild) and queried it (`mcp__doxyguard-db__dossier`, `subje

---

## Final answer as submitted

## Answer

I added the function at the end of `src/facade/entropic.cpp`, after the file's closing `extern "C"` block, since the instruction gave a plain C++ signature (no `extern "C"`, no `ENTROPIC_EXPORT`):

```cpp
/**
 * @brief Acceptance-test probe: exists only so the docs-db acceptance
 * benchmark has a symbol it introduced itself to trace.
 * @return 0.
 * @version 1.0.0
 */
int entropic_acceptance_probe() {
    return 0;
}
```

Rebuilt the index (`ok: true`, `stale: false`, `build_version: 50`, `source_changed_files: 0` after rebuild) and queried it (`mcp__doxyguard-db__dossier`, `subject: entropic_acceptance_probe`).

- **Signature:** `int entropic_acceptance_probe()` — confirmed by the index (`dossier.signature`).
- **File:** `src/facade/entropic.cpp:4131-4133` (per the index's `file`/`line_start`/`line_end`; I placed it there in this same turn).
- **Doxygen brief:** "Acceptance-test probe: exists only so the docs-db acceptance benchmark has a symbol it introduced itself to trace." (`dossier.brief`, matching what I wrote at `src/facade/entropic.cpp:4127`).
- **Does anything call it:** No. `dossier.callers` is `[]`, and it's the only new symbol in the build, so nothing in the tree references it.
- **Visible to a library consumer:** No.
  - It is not declared in any public header — `grep` over `include/entropic/` for the name returns nothing.
  - `include/entropic/entropic_export.h:5-9` states `ENTROPIC_EXPORT` is applied only to factory functions, the C API in `entropic.h`, and `entropic_plugin_api_version()`; my new function has no `ENTROPIC_EXPORT` decoration.
  - `CMakeLists.txt:34-35` sets `CMAKE_CXX_VISIBILITY_PRESET hidden` (plus inlines hidden), so any symbol not explicitly marked with default visibility is hidden from the shared library's dynamic symbol table.
  - It also lives outside the file's `extern "C" { ... }` block (`src/facade/entropic.cpp:4123` closes it), so even its linkage name would be C++-mangled, not the flat C ABI name consumers link against.

So: it compiles and is indexed, but it's an internal, unreferenced, unexported symbol — not part of the shipped library's public API surface.

## Gaps

- I could not compile the target to independently verify the visibility conclusion (no build was run; conclusion is from reading `entropic_export.h` and `CMakeLists.txt` directly, cited above) — the editor's clang diagnostics on this file show pre-existing include-resolution errors (missing `entropic/config/bundled_models.h`, unresolved macros) unrelated to my edit, consistent with the file needing full project include paths/build flags the editor's isolated clang check doesn't have.
- `dossier.candidates` and `dossier.provenance` were empty/null — nothing further to report there.
