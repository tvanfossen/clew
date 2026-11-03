## What gets called

Every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. What those names resolve to depends on the build:

```
library code: mbedtls_calloc(n, sz)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY off (the default)
        │     platform.h:166-167  →  calloc / free from libc
        │
        ├─ MBEDTLS_PLATFORM_MEMORY on, plus both *_MACRO defined
        │     platform.h:143-144  →  MBEDTLS_PLATFORM_CALLOC_MACRO / FREE_MACRO
        │     (no runtime pointers, and platform.c:20-64 is compiled out)
        │
        └─ MBEDTLS_PLATFORM_MEMORY on, macros not both defined
              platform.h:148-149 → real functions in platform.c:47-55
              → (*mbedtls_calloc_func)(n, sz) / (*mbedtls_free_func)(p)
              pointers start as platform.c:44-45 stubs:
                calloc stub returns NULL, free stub does nothing
```

The default `mbedtls_config.h` has `MBEDTLS_PLATFORM_MEMORY` commented out (line 208), so a stock build calls libc directly. Nothing in `library/` calls raw `calloc`/`free`. The only exceptions are comments.

## How a project substitutes its allocator

Three routes, in increasing order of runtime control:

1. **Compile-time macros.** Enable `MBEDTLS_PLATFORM_MEMORY` and define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config, for example `my_calloc` and `my_free`. Both must be defined together, and the macros are honoured only when `MEMORY` is on (platform.h:138-145). The runtime setter is not compiled in at all in this mode, so calling it fails to link.

2. **Compile-time defaults plus runtime override.** Enable `MBEDTLS_PLATFORM_MEMORY` and leave the macros undefined. Define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` if you want a non-null default. The library then exposes `mbedtls_platform_set_calloc_free()` (platform.h:160-161). Call it once, before any library allocation, to install your functions.

3. **Stack/heap buffer allocator.** `mbedtls_memory_buffer_alloc_init(buf, len)` serves allocations from a caller-supplied buffer and never calls libc.

## What the library does with the facility

- **Stores the two pointers** as file-static globals (platform.c:44-45). `mbedtls_platform_set_calloc_free()` just overwrites them (platform.c:57-63). There is no locking, so install the functions before threads start.
- **Calls them through thin wrappers** (platform.c:47-55). Roughly 150 call sites across `library/` and the test helpers use `mbedtls_calloc` / `mbedtls_free`, including the cipher context allocators, the ASN.1 and X.509 parsers, bignum growth, the SSL session and handshake code, and PSA key slots. The index shows about 130 callers of `mbedtls_calloc` alone.
- **Ships its own allocator.** `mbedtls_memory_buffer_alloc_init()` (memory_buffer_alloc.c:566-600) zeroes a global heap context, initialises a mutex if `MBEDTLS_THREADING_C` is set, and calls `mbedtls_platform_set_calloc_free()` with its own `buffer_alloc_calloc` / `buffer_alloc_free` (or the mutexed variants). It is the only library-internal caller of the setter. Calling it therefore overrides whatever the project installed earlier.

## Caveats

- Stub behaviour when `MEMORY` is on but nothing was installed: every allocation fails with NULL. Anything that tries to allocate then reports an error rather than crashing.
- Whichever mode you choose, `mbedtls_free` must accept pointers from `mbedtls_calloc` and must tolerate NULL.
- I did not inspect `tests/configs/user-config-malloc-0-null.h` or the TF-M profile beyond the index's gate listing, so those examples are not verified here.