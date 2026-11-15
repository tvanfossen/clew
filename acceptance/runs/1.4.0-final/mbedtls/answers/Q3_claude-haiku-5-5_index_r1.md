**Short answer:** every allocation in the library goes through two function pointers in `library/platform.c`, reached via `mbedtls_calloc()` and `mbedtls_free()`. Those pointers default to stubs that fail, and a project swaps in its allocator either at build time (macros) or at run time (`mbedtls_platform_set_calloc_free()`).

**What a call resolves to**

```
library code: mbedtls_calloc(n, sz)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY off (the default)
        │     └─ #define mbedtls_calloc calloc      (include/mbedtls/platform.h:166)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY on, CALLOC_MACRO + FREE_MACRO both set
        │     └─ #define mbedtls_calloc MBEDTLS_PLATFORM_CALLOC_MACRO   (platform.h:144)
        │
        └─ MBEDTLS_PLATFORM_MEMORY on, macros not set (runtime mode)
              └─ mbedtls_calloc() in library/platform.c:47
                    └─ (*mbedtls_calloc_func)(n, sz)
                          default = platform_calloc_uninit → always returns NULL
```

The runtime case is the one that matters. In `platform.c:44-45`, `mbedtls_calloc_func` and `mbedtls_free_func` start at `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`. If those are not defined, they fall back to `platform_calloc_uninit` (returns NULL) and `platform_free_uninit` (no-op). `mbedtls_platform_set_calloc_free()` (`platform.c:57-63`) overwrites both pointers.

**How a project substitutes its allocator**

Three options, in order of how early they bind:

1. **Compile-time macros.** In `mbedtls_config.h` (or a `MBEDTLS_USER_CONFIG_FILE`), enable `MBEDTLS_PLATFORM_MEMORY` and define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. Each `mbedtls_calloc`/`mbedtls_free` becomes a direct call to your symbol, with no indirection. The header and `platform.c` both note that this form takes precedence, and `platform.c:20-22` then omits the runtime code entirely. The two macros must be set together.

2. **Runtime function pointers.** Enable `MBEDTLS_PLATFORM_MEMORY` and leave the macros undefined. Then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other mbedtls call. This is the same mechanism the library uses internally (see below).

3. **Standard-named defaults.** Define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` to give the runtime pointers a compile-time initial value, so you need not call the setter at all. Setting them is optional, and they cannot be combined with the `*_MACRO` form.

Requirements from the config docs (`mbedtls_config.h:4120-4134`, `:196-202`): your free must accept NULL and do nothing; any non-NULL pointer must have come from your calloc and not yet been freed; and both pointers must be valid before the first mbedtls allocation, or every allocation silently returns NULL.

**What the library does with the facility**

- **Allocation path.** Library code calls `mbedtls_calloc` / `mbedtls_free` throughout: cipher contexts (`cipher_wrap.c`), ASN.1 and X.509 parsing, bignum growth (`mbedtls_mpi_grow`/`shrink`), ECP, PK, PEM, SSL sessions and buffers, and PSA slots. The dossier reports about 133 callers of `mbedtls_free` alone. I found no bare `malloc`/`calloc` in `library/` outside comments, with one exception below.

- **Built-in allocator.** `library/memory_buffer_alloc.c` is a stack-style heap over a caller-provided buffer. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) calls `mbedtls_platform_set_calloc_free()` with its own `buffer_alloc_calloc` / `buffer_alloc_free`, or the `_mutexed` variants when `MBEDTLS_THREADING_C` is on. So the library's own heap is just another runtime substitution, and that is how it is used in `programs/test/benchmark.c`.

- **One exception.** `memory_buffer_alloc.c:404` contains `free(hdr->trace)`, a direct libc call. I did not confirm which guard encloses it, so I can't say whether it runs in a normal build.

**Caveats**

- Runtime substitution is global state. Set it once, before any thread starts. The index shows threads spawned in `programs/ssl/ssl_pthread_server.c`, and the buffer allocator's mutex only exists under `MBEDTLS_THREADING_C`.
- Macro mode and runtime mode are mutually exclusive in practice. Pick one per build.
- I did not run a build or test to confirm the macro-mode and runtime-mode behaviour. The conclusions above come from reading the source and the index.