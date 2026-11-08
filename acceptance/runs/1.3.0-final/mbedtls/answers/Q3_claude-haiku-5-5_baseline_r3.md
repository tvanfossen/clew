**Short answer:** every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. What those names resolve to depends on the build configuration. By default they are the C library's `calloc` and `free`. A project can swap in its own functions at compile time or at runtime.

**What gets called**

- **Default (`MBEDTLS_PLATFORM_MEMORY` off):** `include/mbedtls/platform.h:163-167` makes `mbedtls_calloc` a macro for `calloc` and `mbedtls_free` a macro for `free`. The library calls libc directly.
- **Compile-time override (`MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`):** `platform.h:139-144` makes the two names macros for your functions. Calls are resolved at compile time, with no indirection.
- **Runtime override (`MBEDTLS_PLATFORM_MEMORY` on, macros not defined):** `platform.h:146-162` declares real functions `mbedtls_calloc()` and `mbedtls_free()`. `library/platform.c:44-63` implements them as calls through two function pointers. `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` swaps the pointers.

**Fallback when no override is set**

`library/platform.c:24-42` fills in placeholders when `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` are not defined. The placeholder calloc returns `NULL`, so allocation fails cleanly. The placeholder free does nothing. Without a set call, a runtime-configured build therefore cannot allocate. The documented rule is in `include/mbedtls/mbedtls_config.h:165-201`.

**How a project substitutes its allocator**

1. **Compile-time:** enable `MBEDTLS_PLATFORM_MEMORY` in its config and define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to its functions. Both macros must be defined together. `check_config.h:558-573` enforces that.
2. **Runtime:** enable `MBEDTLS_PLATFORM_MEMORY` without the macros. Call `mbedtls_platform_set_calloc_free()` before any library call that allocates. Alternatively, define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` to set the initial values.

Precedence: the compile-time macros win. `platform.c:16-19` says so, and it compiles out the runtime setter entirely in that case.

**What the library does with the facility itself**

- Every library allocation goes through `mbedtls_calloc()` / `mbedtls_free()`. Examples: `library/ecp.c`, `library/rsa.c`, `library/md.c`, `library/x509_crl.c`, `library/ssl_cache.c`.
- The library never calls `calloc`/`malloc` directly. Swapping the functions therefore changes allocation for the whole library at once.
- The one built-in allocator is `library/memory_buffer_alloc.c`. `mbedtls_memory_buffer_alloc_init(buf, len)` (line 566) serves allocations from a caller-supplied buffer. As a side effect it calls `mbedtls_platform_set_calloc_free()` to install its own functions. That install is global, so it changes the allocator for the whole process, not just one context. With `MBEDTLS_THREADING_C` it installs mutex-wrapped versions.
- The library does not allocate anything itself to hold a secret. Zeroing goes through `mbedtls_platform_zeroize()`, which is separate from the allocator.

**Caveats**

- A project must install its allocator before any library call that allocates. Otherwise the placeholder returns `NULL`.
- The runtime pointers are global and unsynchronized. Setting them while another thread is inside the library is unsafe unless the project provides its own locking. The buffer allocator's mutex wrapper is one example of that kind of locking.
- Mixing allocators is a bug. Memory from one `calloc` must be freed by the matching `free`. Changing the allocator while live objects exist will corrupt them.

I did not run a build or the test suite. The above is from reading `platform.c`, `platform.h`, `mbedtls_config.h`, `check_config.h`, and `memory_buffer_alloc.c`.