**Short answer:** by default, `mbedtls_calloc` and `mbedtls_free` are macros that expand to the C library's `calloc` and `free`. Every allocation in the library goes through those two names. A project can swap them at compile time with macros, or at run time with a function-pointer setter. The library's own built-in heap (`memory_buffer_alloc`) is just one implementation that plugs into the same setter.

**What gets called**

- **Default (`MBEDTLS_PLATFORM_MEMORY` off):** `include/mbedtls/platform.h:166-167` defines `mbedtls_free` as `free` and `mbedtls_calloc` as `calloc`. The default for `MBEDTLS_PLATFORM_MEMORY` is commented out in `include/mbedtls/mbedtls_config.h:208`.
- **Compile-time macros (`MBEDTLS_PLATFORM_MEMORY` + `MBEDTLS_PLATFORM_CALLOC_MACRO` + `MBEDTLS_PLATFORM_FREE_MACRO`):** `platform.h:143-144` makes `mbedtls_calloc` and `mbedtls_free` expand straight to your functions. No wrapper, no runtime indirection.
- **Run-time hook (`MBEDTLS_PLATFORM_MEMORY` alone, macros undefined):** `platform.h:148-161` declares real functions `mbedtls_calloc`/`mbedtls_free` plus `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)`. In `library/platform.c:44-63` these are implemented as thin wrappers that call through two static function pointers. Those pointers default to `MBEDTLS_PLATFORM_STD_CALLOC`/`_STD_FREE`, which resolve to `calloc`/`free` unless you override them.
- **Edge case:** if `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set and no std calloc/free is provided, the defaults are `platform_calloc_uninit` (returns NULL) and `platform_free_uninit` (no-op), per `platform.c:24-42`. Allocations fail until you call the setter. The config doc at `mbedtls_config.h:199-202` describes the same behavior.

**How a project substitutes its allocator**

Option A, compile time (no runtime cost, usual for RTOS or embedded builds):
1. Enable `MBEDTLS_PLATFORM_C` and `MBEDTLS_PLATFORM_MEMORY`.
2. Define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in your config. They must be set together; `include/mbedtls/check_config.h:558-573` enforces this, along with the mutual exclusion with `*_STD_*`.
3. Provide the named functions and link them in.

Option B, run time:
1. Enable `MBEDTLS_PLATFORM_MEMORY` without the macros.
2. Early in `main`, call `mbedtls_platform_set_calloc_free(my_calloc, my_free)`. Call it before any Mbed TLS allocation, since the default is the uninit stub or libc.

The `alternative-implementations.md` doc (lines 80-91) describes the same `MBEDTLS_PLATFORM_XXX_ALT` pattern, but calloc/free are the paired case that uses the compile-time macros or `set_calloc_free`.

**What the library does with the facility**

- Almost every allocation site uses the wrapped names. A rough count is 358 call sites across 50 files in `library/`. Examples: `ssl_tls.c` allocates `transform_negotiate`, `session_negotiate` and `handshake` at lines 1085-1094, and `x509_crt`, `psa_crypto` and the PK/EC modules follow the same pattern.
- A grep for bare `calloc(`, `free(`, `malloc(` in `library/` finds nothing that allocates. The only hits are a comment in `base64.c`, comments in `bignum.c`, and `free(hdr->trace)` in `memory_buffer_alloc.c:404`, which is in the debug trace path. So the library does not bypass the hook.
- `library/memory_buffer_alloc.c` is the library's own allocator. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) takes a caller-supplied static buffer, zeroes it, builds a header-linked free list, and then registers its own `buffer_alloc_calloc`/`buffer_alloc_free` through `mbedtls_platform_set_calloc_free` (`:572-575`). When `MBEDTLS_THREADING_C` is on, it registers mutex-wrapped versions instead (`:541-563`), and it locks around each call. This is the library using its own run-time facility to install a heap-backed allocator, so the whole library draws from that buffer with no libc involved.
- `mbedtls_memory_buffer_alloc_free()` (`:602-608`) tears down the mutex and zeroes the heap context. It does not restore the libc defaults, so after it runs the hook still points at the buffer allocator.

**Caveats**

- The compile-time macro path is not a runtime override. If you define the macros, `mbedtls_platform_set_calloc_free` is compiled out (`platform.c:20-22`), so the setter has no effect.
- The hook is one global pair of pointers. It is not per-context and not thread-safe to change while the library is running.
- I did not build or run anything. This is from reading the headers and `platform.c`, plus grep over `library/`.