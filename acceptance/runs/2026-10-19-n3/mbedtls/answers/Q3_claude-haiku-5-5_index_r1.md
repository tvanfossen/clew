**Short answer:** every allocation inside mbedtls goes through `mbedtls_calloc()` / `mbedtls_free()`. What those two names resolve to depends on the build configuration. By default they are libc `calloc`/`free`. A project can replace them at compile time with macros, or at runtime with a function-pointer setter. The library itself never calls `malloc`/`free` directly, with one debug-only exception.

**What gets called**

| Config | `mbedtls_calloc` resolves to | Where |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` not defined (default) | `calloc` (macro) | `include/mbedtls/platform.h:166-167` |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | your macro | `platform.h:143-144` |
| `MBEDTLS_PLATFORM_MEMORY` alone | real function `mbedtls_calloc()` in `library/platform.c:47`, which calls through a function pointer | `platform.c:44-50` |

In the function-pointer case, the pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE`. If those are not defined, they default to stubs that fail or do nothing (`platform.c:24-45`). So a build with `MBEDTLS_PLATFORM_MEMORY` but no allocator set at runtime returns NULL from every allocation.

**How a project substitutes its allocator**

- **Compile time:** define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free` in its `mbedtls_config.h` or user config. The macros must be defined as a pair. Every `mbedtls_calloc` call site is then rewritten by the preprocessor, and the runtime setter is compiled out (`platform.c:20-22`).
- **Runtime:** define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other mbedtls call (`platform.c:57-63`, declared at `platform.h:160`). The pointers are plain globals, so this is not thread-safe to change after use.

The contract for the replacement is in `mbedtls_config.h:4113-4133`. `calloc` must zero the memory. `free(NULL)` must be a no-op.

**What the library does with the facility**

- All library allocations are `mbedtls_calloc`/`mbedtls_free` calls. The index shows well over a hundred callers, covering context allocation in the cipher modules (`aes_ctx_alloc`, `gcm_ctx_alloc`), bignum growth (`mbedtls_mpi_grow`), SSL handshake state, X.509 and PKCS#7 parsing, and PSA key slots.
- A grep of `library/` for raw `calloc`/`malloc`/`realloc`/`free` finds no direct calls, apart from the one below.
- The exception is `library/memory_buffer_alloc.c:404`. Under `MBEDTLS_MEMORY_BACKTRACE`, the block header's `trace` string from `backtrace_symbols()` is released with libc `free()`. That is a debug-only path, and libc's `backtrace_symbols` itself uses libc `malloc`.
- The library ships its own consumer of the facility. `mbedtls_memory_buffer_alloc_init()` (`memory_buffer_alloc.c:566-600`) takes a caller-supplied buffer and installs its own allocator by calling `mbedtls_platform_set_calloc_free()`. It uses a mutex-wrapped variant when `MBEDTLS_THREADING_C` is on. This gives a heap with no libc dependency. It is the intended path for embedded targets that have no heap.

**Two things to watch**

- Because allocation is routed through `mbedtls_calloc`, a leak or double-free in a custom allocator shows up in the library's own paths, not in your code. Pair the allocator with `MBEDTLS_MEMORY_DEBUG` if you need to see what is in use.
- The runtime setter is not guarded. Installing a new allocator while contexts from the old one are live will free memory through the wrong function. Set it once, before `mbedtls_*_init` or any context allocation.