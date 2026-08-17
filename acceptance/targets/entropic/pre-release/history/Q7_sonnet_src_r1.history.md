# Q7 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=grep -n "^int\|^static\|^}" ~/ddb-targets/entropic/src/facade/entropic.cpp | tail -30; echo ---; wc -l ~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 3408:} 3439:} 3467:} 3490:} 3509:} 3518:int entropic_check_mcp_key( 3530:} 3559:} 3581:} 3602:} 3621:} 3654:} 3686:} 3704:} 3730:} 3749:} 3770:} 3818:} 3851:} 3871:} 3886:int entropic_model_has_vision( 3903:} 3922:} 3943…

### 2. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 4080	                     tier_name.c_str(), 4081	                     model_path.c_str(), 4082	                     footprint, 4083	                     user_data); 4084	        }; 4085	    } 4086	    if (handle->orches…

### 3. `Bash`
- **asked:** command=ls ~/ddb-targets/entropic/src/facade/; echo ---; find ~/ddb-targets/entropic -iname "*.h" -path "*facade*" -o -iname "entropic.h" 2>/dev/null; echo ---; grep -rn "entropic_check_mcp_key\|entropic_model_has_vision" ~/ddb-targets/entropic --include=*.h -l
- **got:** CMakeLists.txt conversation_state.h engine_handle.h entropic_audit.cpp entropic_compaction.cpp entropic.cpp entropic_hooks.cpp entropic_identity.cpp entropic_mcp.cpp entropic_storage.cpp external_bridge.cpp json_serializ…

### 4. `Bash`
- **asked:** command=grep -n "entropic_residency_snapshot\|ENTROPIC_API\|__attribute__\|visibility\|extern \"C\"" ~/ddb-targets/entropic/include/entropic/entropic.h | head -30
- **got:** 54:extern "C" { 187: * Compare with ENTROPIC_API_VERSION at compile time for version checks. 194: * @see ENTROPIC_API_VERSION (compile-time constant in entropic_config.h) 761: * `entropic_residency_snapshot`. 819:ENTROPI…

### 5. `Bash`
- **asked:** command=grep -n "ENTROPIC_EXPORT" ~/ddb-targets/entropic/include/entropic/*.h ~/ddb-targets/entropic/include/entropic/**/*.h 2>/dev/null echo --- grep -rn "VISIBILITY\|fvisibility\|CXX_VISIBILITY" ~/ddb-targets/entropic/CMakeLists.txt ~/ddb-targets/entropic/src/facade/CMakeLists.txt 2>/dev/null
- **got:** ~/ddb-targets/entropic/include/entropic/entropic_export.h:20:    #define ENTROPIC_EXPORT ~/ddb-targets/entropic/include/entropic/entropic_export.h:23:        #define ENTROPIC_EXPORT __declspec(dllexport) ~/ddb-targets/en…

**Reasoning.** Confirmed: visibility preset is `hidden` and only `ENTROPIC_EXPORT`-tagged symbols are exported. Now add the function.

### 6. `Edit`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** The file ~/ddb-targets/entropic/src/facade/entropic.cpp has been updated successfully. (file state is current in your context — no need to Read it back)

### 7. `Bash`
- **asked:** command=grep -rn "entropic_acceptance_probe" ~/ddb-targets/entropic --include=*.cpp --include=*.h --include=*.hpp
- **got:** ~/ddb-targets/entropic/src/facade/entropic.cpp:4131:int entropic_acceptance_probe() {

**Reasoning.** These diagnostics stem from clangd's include-path resolution (missing generated headers like `bundled_models.h`), not from my edit — the errors are all on pre-existing lines unrelated to the appended function.

## Answer

**Signature:** `int entropic_acceptance_probe()` (extern "C" linkage, no parameters) — added at `src/facade/entropic.cpp:4131`.

**File:** `src/facade/entropic.cpp`, inside the same `extern "C" { ... }` block (opened earlier in the file) as all the other facade entry points such as `entropic_residency_snapshot` (`src/facade/entropic.cpp:4104`) and `entropic_check_mcp_key` (`s

---

## Final answer as submitted

These diagnostics stem from clangd's include-path resolution (missing generated headers like `bundled_models.h`), not from my edit — the errors are all on pre-existing lines unrelated to the appended function.

## Answer

**Signature:** `int entropic_acceptance_probe()` (extern "C" linkage, no parameters) — added at `src/facade/entropic.cpp:4131`.

**File:** `src/facade/entropic.cpp`, inside the same `extern "C" { ... }` block (opened earlier in the file) as all the other facade entry points such as `entropic_residency_snapshot` (`src/facade/entropic.cpp:4104`) and `entropic_check_mcp_key` (`src/facade/entropic.cpp:3518`). It's the last function before the block closes at `src/facade/entropic.cpp:4142`.

**Doxygen brief:** "Acceptance-test probe: a trivial no-op sentinel used to verify the docs.db pipeline can pick up a freshly added translation-unit local function." (`src/facade/entropic.cpp:4123-4130`)

**Does anything call it?** No. `grep -rn "entropic_acceptance_probe"` across all `.cpp`/`.h`/`.hpp` files in the repo returns only its own definition line (`src/facade/entropic.cpp:4131`) — no call sites anywhere.

**Visible to a consumer linking against the shipped library?** No. Two independent reasons:
1. It is **not declared in the public header** `include/entropic/entropic.h`, which is the header consumers include — every other facade function (`entropic_residency_snapshot` at `include/entropic/entropic.h:819`, `entropic_check_mcp_key` at `include/entropic/entropic.h:1804`, etc.) has a matching declaration there; `entropic_acceptance_probe` has none.
2. Even if it were called internally, the build sets `CMAKE_CXX_VISIBILITY_PRESET hidden` and `CMAKE_VISIBILITY_INLINES_HIDDEN ON` (`CMakeLists.txt:34-35`), so only symbols explicitly marked `ENTROPIC_EXPORT` (`__attribute__((visibility("default")))`, defined in `include/entropic/entropic_export.h:28`) are exported from the shared library. `entropic_acceptance_probe` carries no `ENTROPIC_EXPORT` marker, so it would have hidden visibility and not appear in the shared library's dynamic symbol table even if a header existed.

So it compiles into the object file but is neither declared for public use nor exported at the linker level — a consumer cannot see or call it.

## Gaps

- I did not build the project to empirically confirm the symbol is absent from `nm -D` on the built `.so`; this is inferred from the `hidden` visibility preset and lack of `ENTROPIC_EXPORT`/header declaration, both of which are consistent and load-bearing for every other function in the file.
- Only source-tree grep was used to check for callers; no build-time call graph or link-time symbol table was consulted.
