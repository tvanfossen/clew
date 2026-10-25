Every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`, never directly through `calloc()`/`free()`. What those two names resolve to depends on the build configuration. The sites I grepped in `library/` (e.g. `x509.c:531`, `bignum.c:218`, `pem.c:422`) all use `mbedtls_calloc`. I did not exhaustively check for raw `calloc(` calls in the library.

**What gets called, by configuration**

| Configuration | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | The libc `calloc` / `free`, via macros in `include/mbedtls/platform.h:164-167`. No indirection. |
| `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Those macro names, substituted at compile time (`platform.h:139-144`). |
| `MBEDTLS_PLATFORM_MEMORY` only | Real functions in `library/platform.c:47-55` that call through the function pointers `mbedtls_calloc_func` / `mbedtls_free_func`. Those pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE`. |

With the third row, the defaults are libc `calloc`/`free` unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set. If it is set and nothing else is provided, the defaults are `platform_calloc_uninit` (always returns NULL) and `platform_free_uninit` (no-op) (`platform.c:24-42`, `mbedtls_config.h:4113-4134`). So a platform with no `malloc` fails cleanly rather than failing to link.

**How a project substitutes its allocator**

Compile-time, with the allocator fixed at build time:
- Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. `check_config.h:558-573` enforces that the two macros are set together and that `CALLOC_MACRO` cannot be combined with `STD_CALLOC`.
- Alternatively, keep the runtime mechanism and only set `MBEDTLS_PLATFORM_STD_CALLOC=my_calloc`. `tests/configs/user-config-malloc-0-null.h:21` does this.

Runtime, with the allocator chosen at startup:
- Define only `MBEDTLS_PLATFORM_MEMORY`.
- Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any library allocation (`platform.c:57-63`).
- The function sets two plain globals and takes no lock, so it must not race with library use.
- The replacement `calloc` must zero memory, and `free(NULL)` must be a no-op (`mbedtls_config.h:4116, 4129`).
- Do not free a block with a different allocator than the one that produced it.

**What the library does with the facility**

- `platform.c` never allocates. It only stores the two pointers and dispatches through them.
- `memory_buffer_alloc.c` is the library's own client of this hook. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-576`) zeroes its bookkeeping, then calls `mbedtls_platform_set_calloc_free()` with its own `buffer_alloc_calloc` / `buffer_alloc_free`. With `MBEDTLS_THREADING_C` it uses mutex-wrapped variants. From then on, every library allocation is served from the caller's static buffer. The allocator is global, so this affects the whole process. A later `mbedtls_platform_set_calloc_free()` call silently replaces it, and the buffer heap is then no longer used.
- `mbedtls_memory_buffer_alloc_init` is documented as "sets the global mbedtls_calloc() and mbedtls_free() pointers" (`memory_buffer_alloc.h:41-48`). The `docs/architecture/alternative-implementations.md:91` note describes the same calloc/free pairing.
- `programs/test/udp_proxy.c:27` shows the compile-time pattern in a sample program. `programs/test/selftest.c` exercises `mbedtls_calloc(0, 1)` and related edge cases, which covers the zero-size behaviour the contract allows.