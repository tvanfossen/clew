**Short answer:** the library never calls `malloc`, `calloc` or `free` directly. Every allocation goes through `mbedtls_calloc(n, size)` and every release through `mbedtls_free(ptr)`. What those two names resolve to is decided at build time by the platform layer.

**What gets called**

- Without `MBEDTLS_PLATFORM_MEMORY`, `include/mbedtls/platform.h:163-167` makes them plain macros: `mbedtls_calloc` → `calloc`, `mbedtls_free` → `free`. There is no indirection.
- With `MBEDTLS_PLATFORM_MEMORY`, there are two ways to choose the allocator:
  1. **Compile time:** define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. `platform.h:139-144` then maps `mbedtls_calloc`/`mbedtls_free` straight to your functions. `check_config.h:558-573` requires the two to be defined together.
  2. **Run time:** leave the macros undefined. `platform.h:145-160` declares `mbedtls_calloc()`/`mbedtls_free()` as real functions and `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)`. In `library/platform.c:44-63`, those functions are thin wrappers around two function pointers. The pointers start at `MBEDTLS_PLATFORM_STD_CALLOC`/`STD_FREE`, which default to `calloc`/`free`. If `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set, they start as stubs: calloc returns NULL and free does nothing.

If both macros are defined, `platform.c:20-22` compiles out the whole runtime mechanism, so `mbedtls_platform_set_calloc_free` is not declared or available.

**How a project substitutes its allocator**

- Compile-time, the simplest route: in the config header, define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. Make sure those functions are visible to every translation unit.
- Runtime: define `MBEDTLS_PLATFORM_MEMORY` only. Early in startup, before any Mbed TLS call that allocates, call `mbedtls_platform_set_calloc_free(my_calloc, my_free)`. The setter writes two unsynchronised globals (`platform.c:60-61`), so it should run once, single-threaded.
- Changing only the default target: `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` set what the runtime pointers start as. The repo's own example, `tests/configs/user-config-malloc-0-null.h`, does this: it defines `MBEDTLS_PLATFORM_MEMORY` and `MBEDTLS_PLATFORM_STD_CALLOC=custom_calloc`, where `custom_calloc` returns NULL for zero-sized requests. It is a test config, not a template for production allocators.

**What the library itself does with the facility**

- **Allocation sites:** these are spread through the code. For example, `psa_crypto.c` calls `mbedtls_calloc(1, ...)` for key buffers, HKDF info and PRF seeds, and the matching `mbedtls_free` calls follow.
- **Zeroing is the library's job.** The hook only supplies memory. The library calls `mbedtls_platform_zeroize` before freeing secrets; for example, `ssl_msg.c` wipes MAC buffers at lines 1109, 1450, 1815 and 2081–2082. Any replacement allocator is not expected to scrub memory.
- **Built-in allocator as a client:** `library/memory_buffer_alloc.c` is an allocator the library ships. `mbedtls_memory_buffer_alloc_init(buf, len)` (line 566) calls `mbedtls_platform_set_calloc_free` with its own functions, locking them if threading is enabled. The global allocator is therefore replaced at init, and `mbedtls_memory_buffer_alloc_free` (line 602) zeroes its heap context. Because it overwrites the same global pointers, it conflicts with an application's own `set_calloc_free` call.
- **Zero-size requests:** `base64.c` and `psa_crypto.c` have comments noting that `malloc(0)` may return NULL. The library avoids zero-size calls, and the `user-config-malloc-0-null.h` test checks that it tolerates NULL from calloc.
- **Same pattern elsewhere:** `platform.c` uses the identical `XXX_ALT` plus function-pointer approach for printf, snprintf, time, exit, NV seed and others. `docs/architecture/alternative-implementations.md:80-91` describes it.

**One detail I did not verify:** whether every call site in the library genuinely depends on calloc's zeroed result, rather than just happening to be zeroed. The signature is calloc-shaped, so a replacement should return zeroed memory, but I did not audit each site.