# Q7 — src — sonnet — run 1

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
