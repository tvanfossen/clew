**Short answer:** every allocation in the library goes through `mbedtls_calloc()` / `mbedtls_free()`. What those two resolve to depends on the build configuration. With the shipped defaults, they are the libc `calloc` and `free`.

**What gets called**

The chain depends on `MBEDTLS_PLATFORM_MEMORY` and the two `MBEDTLS_PLATFORM_{CALLOC,FREE}_MACRO` options (`include/mbedtls/platform.h:138-168`):

| Config | `mbedtls_calloc` resolves to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (shipped default, `mbedtls_config.h:208` commented out) | the libc `calloc`, by macro (`platform.h:166-167`) |
| `MBEDTLS_PLATFORM_MEMORY` on, both `*_CALLOC_MACRO` and `*_FREE_MACRO` defined | your macro, substituted at compile time (`platform.h:143-144`) |
| `MBEDTLS_PLATFORM_MEMORY` on, macros not both defined | a real function `mbedtls_calloc()` in `library/platform.c:47-50`, which calls through a function pointer |

In the third case the pointer starts as `MBEDTLS_PLATFORM_STD_CALLOC`. If that is not defined, it is the stub `platform_calloc_uninit`, which always returns NULL (`platform.c:24-33, 44`). The same applies to free, where the stub does nothing. So an unconfigured dynamic build fails every allocation rather than silently using libc.

**How a project substitutes its allocator**

Three routes, in order of how early they bind:

1. **Compile-time macros.** Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config. The macros must be defined together; the header comment at `mbedtls_config.h:197-198` says so. Calls are replaced at compile time with no runtime indirection.
2. **Runtime registration.** Define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any library call. It stores the two pointers in `platform.c:57-63`. The setter takes no lock, so it must run before threads start.
3. **Default function, replaced at build time.** Define `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` in config, and the dynamic path uses them as the initial values (`mbedtls_config.h:4113-4134`).

The contract for a replacement is documented in `mbedtls_config.h:4113-4133`: calloc must zero memory and return NULL on failure; free must accept NULL; a non-NULL argument must be a pointer your calloc returned and not yet freed.

**What the library does with the facility**

- **Allocation sites.** The library never calls `malloc`, `calloc` or `free` directly. A grep of `library/` finds only comments and one debug-only `free(hdr->trace)` in `memory_buffer_alloc.c:404`, which frees the `backtrace_symbols` output. Every ctx allocator, ASN.1 and X.509 parser, bignum growth, PSA slot and key buffer, and SSL session/handshake object goes through `mbedtls_calloc`. The dossier's caller list for `mbedtls_calloc` runs to over 100 functions.
- **Its own allocator.** The library ships `library/memory_buffer_alloc.c`, a fixed-buffer heap. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) calls `mbedtls_platform_set_calloc_free()` with its own functions. With `MBEDTLS_THREADING_C` it installs mutex-wrapped versions (`buffer_alloc_calloc_mutexed`, lines 541-552). The buffer is then the only heap. Because the setter is global, calling this at init replaces whatever allocator was there before.
- **Self-test.** `mbedtls_memory_buffer_alloc_self_test` calls `mbedtls_calloc` directly, so it exercises whatever allocator is installed.

**Points to watch when substituting**

- Do not call `mbedtls_platform_set_calloc_free` after threads start or after the first allocation; the library reads the pointers without synchronization.
- `mbedtls_memory_buffer_alloc_init` and the setter overwrite the same global, so use one or the other, not both.
- With the compile-time macros set, `mbedtls_platform_set_calloc_free` is compiled out (`platform.c:20-22`); calling it then is a link error, not a silent no-op.

I did not build or run any of these configurations, so the behaviour above is from reading the code and the index's dossier output.