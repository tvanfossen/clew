# Q7 — src — haiku — run 1

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
