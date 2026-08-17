# Q7 — mcp — haiku — run 1

## Final Answer

Given the conflicting instructions ("Do not write files" vs. "Add a function"), I'm interpreting this as a hypothetical assessment based on the existing codebase patterns:

**If `entropic_acceptance_probe` were added to `src/facade/entropic.cpp` as specified:**

1. **Signature**: `int entropic_acceptance_probe();` (no parameters, returns int)

2. **File**: `src/facade/entropic.cpp:` (as specified in the question)

3. **Doxygen brief**: "Acceptance-test probe" (as specified in the question)

4. **Does anything call it**: **No** — The function does not currently exist in the codebase. A search of the index returned zero results for `entropic_acceptance_probe`. No code calls a non-existent function.

5. **Visible to consumer linking against the shipped library**: **No** — Based on the existing API pattern (demonstrated by `entropic_create` at `src/facade/entropic.cpp:241` which is declared in the public header `include/entropic/entropic.h:73` with `ENTROPIC_EXPORT`), a function defined only in the implementation file without a corresponding declaration in the public header would NOT be visible to consumers. The public API surface is strictly controlled by declarations in `include/entropic/entropic.h` preceded by the `ENTROPIC_EXPORT` macro.

## Gaps

- I could not determine whether the function **would be callable by internal test code** within the codebase without seeing the complete definition (as static vs. extern "C" affects linkage).
- I interpreted "Do not write files" as a constraint preventing actual code modification, so I answered based on hypothetical analysis rather than adding the function and re-querying the index.
