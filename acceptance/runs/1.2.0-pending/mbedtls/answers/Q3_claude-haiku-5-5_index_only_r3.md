**Short answer:** with the default build, `mbedtls_calloc` and `mbedtls_free` are thin wrappers around a pair of function pointers in `library/platform.c`. A project swaps its allocator by calling `mbedtls_platform_set_calloc_free()`, or, at compile time, by defining its own macros. The library's only use of this facility is its own stack-based allocator, `mbedtls_memory_buffer_alloc_init`.

**What actually gets called**

Which symbol a library call reaches depends on the build. The index's gate data gives three cases (I inferred the header logic from the gate spans, not by reading `platform.h`):

```
library code calls mbedtls_calloc(n, sz)
  │
  ├─ MBEDTLS_PLATFORM_MEMORY undefined ─────────► calloc() directly (platform.h:167)
  │
  ├─ MEMORY + CALLOC_MACRO and FREE_MACRO set ──► the user's macro, bound at compile time (platform.h:144)
  │
  └─ MEMORY, no macros ─► mbedtls_calloc() in platform.c:47
                           └─ (*mbedtls_calloc_func)(n, sz)
```

- `mbedtls_calloc_func` is a static pointer (platform.c:44). It is initialised to `MBEDTLS_PLATFORM_STD_CALLOC`.
- `MBEDTLS_PLATFORM_STD_CALLOC` is `calloc` by default (platform.h:84). With `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` set, it becomes `platform_calloc_uninit` (platform.c:25–30), which always returns NULL. The index's config default for this symbol is a heuristic, because no config header is recorded for this target, so verify it against `mbedtls_config.h`.
- `mbedtls_free` mirrors this through `mbedtls_free_func` (platform.c:52–55).

**How a project substitutes its allocator**

1. **Runtime, the common route.** Enable `MBEDTLS_PLATFORM_C` and `MBEDTLS_PLATFORM_MEMORY` but not the two macros. Then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (platform.c:57–63) before any allocation. The function stores both pointers and returns 0. Nothing locks around the swap, so call it before threads start.
2. **Compile time.** Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config. Every call site then expands to your function directly, with no pointer indirection. The index has no definition site for these two macros, which is expected, since the project supplies them.
3. **Default target only.** Override `MBEDTLS_PLATFORM_STD_CALLOC` (and the free equivalent) to change what the default pointer points at. The repo's test fixture `tests/configs/user-config-malloc-0-null.h` does this with a `custom_calloc` that returns NULL for zero sizes and otherwise calls `calloc`.

**What the library does with the facility**

- Almost all library allocations go through the `mbedtls_calloc`/`mbedtls_free` macros, not `calloc`/`free`. The callers include the cipher, PK, X.509, ASN.1, PSA and SSL modules.
- `mbedtls_memory_buffer_alloc_init` (memory_buffer_alloc.c:566) is the library's own use of the hook. It zeroes its heap, creates a mutex when `MBEDTLS_THREADING_C` is set, and installs its own functions through `mbedtls_platform_set_calloc_free`. It uses the mutexed variants when threading is on, and the plain ones otherwise. It then aligns the caller's buffer and carves allocations from it, so no `calloc` or `free` is needed.
- Possible defect: the hooks are installed before the early return for a buffer that is too small (`len < sizeof(memory_header) + MBEDTLS_MEMORY_ALIGN_MULTIPLE`). In that case the process is left with allocator hooks that point at an uninitialised heap. Worth a look, though I have not checked the caller's handling of that case.