# Q10 — src — haiku — run 1

Based on my analysis of the mbedtls codebase, I found several instances of functions that write to shared state which other functions later read, with no direct call relationship between the writing and reading functions:

## Primary Coupling: Debug Threshold

**Writer:** `mbedtls_debug_set_threshold` (library/debug.c:36-39) writes to global `debug_threshold` at line 38.

**Readers:** Multiple functions read `debug_threshold` with no call from `mbedtls_debug_set_threshold`:
- `mbedtls_debug_print_msg` (library/debug.c:63-95) reads at line 76
- `mbedtls_debug_print_ret` (library/debug.c:97-123) reads at line 106
- `mbedtls_debug_print_buf` (library/debug.c:125-178) reads at line 136
- `mbedtls_debug_print_ecp` (library/debug.c:181-199) reads at line 190
- `mbedtls_debug_print_psa_ec` (library/debug.c:243-271) reads at line 254
- `mbedtls_debug_print_mpi` (library/debug.c:275-389) reads at line 287
- `mbedtls_debug_print_crt` (library/debug.c:394-422) reads at line 405

**Pattern:** A typical usage flow is `mbedtls_debug_set_threshold(level)` called once during initialization, followed by multiple independent debug print function calls that check this threshold. No function-to-function calls exist between the setter and the various getters.

---

## Platform Function Pointers

**Writers/Readers in library/platform.c:**
- `mbedtls_platform_set_calloc_free` (line 57-62) writes `mbedtls_calloc_func` and `mbedtls_free_func`
- `mbedtls_calloc` (line 47-50) reads `mbedtls_calloc_func`
- `mbedtls_free` (line 52-55) reads `mbedtls_free_func`

Similar patterns exist for:
- `mbedtls_platform_set_snprintf` → `mbedtls_snprintf` reader
- `mbedtls_platform_set_printf` → `mbedtls_printf` reader
- `mbedtls_platform_set_fprintf` → `mbedtls_fprintf` reader

**Pattern:** Platform abstractions are typically set once at startup, then used throughout the codebase without callbacks to the setup functions.

---

## MPS Trace Depth Counter

**Coupling in library/mps_trace.c:**
- `trace_depth` global at line 19
- `mbedtls_mps_trace_inc_depth` (line 66-68) writes to it
- `mbedtls_mps_trace_dec_depth` (line 62-64) writes to it
- `mbedtls_mps_trace_get_depth` (line 58-61) reads it

**Pattern:** No call relationship enforced between increment/decrement operations and the read operation across different functions.

---

## Gaps

I could not identify a comprehensive call graph to definitively rule out all indirect call paths without an indexed database. The analysis assumes that absence of direct function calls in the source means no coupling, but complex multi-level indirection or conditional compilation might create hidden call paths not visible through simple text search.
