## Short answer

Every library allocation goes through `mbedtls_calloc()` / `mbedtls_free()`. Those are either compile-time macros or thin wrappers around a global function-pointer pair, which defaults to the C library. A project substitutes its allocator either at build time (define two macros) or at runtime (`mbedtls_platform_set_calloc_free()`). The library ships one built-in replacement, a stack-style heap over a caller-supplied buffer, which works by calling that same runtime setter.

## Call path

```
library code (cipher_wrap, pk_wrap, ssl_tls, x509, bignum, psa, ...)
  -> mbedtls_calloc(n, size)            [platform.h:144 macro, or function]
       MBEDTLS_PLATFORM_CALLOC_MACRO defined?  -> that macro (compile-time)
       otherwise                         -> mbedtls_calloc()   [platform.c:47]
                                              -> (*mbedtls_calloc_func)(n, size)
                                                  default: MBEDTLS_PLATFORM_STD_CALLOC
```

`mbedtls_free()` (`platform.c:52`) mirrors this through `mbedtls_free_func`. The index lists about 70 library callers of `mbedtls_free`, and the `mbedtls_calloc` caller list is similar, so the library does not call `calloc`/`free` directly in those paths. I did not verify that across every file.

## Substituting an allocator

Two mechanisms, both gated by `MBEDTLS_PLATFORM_MEMORY` (default off in `mbedtls_config.h:208`, per the index):

| Mechanism | How | Dispatch |
|---|---|---|
| Compile-time | Enable `MBEDTLS_PLATFORM_MEMORY`, define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Macro expands directly; no pointer indirection |
| Runtime | Enable `MBEDTLS_PLATFORM_MEMORY` without the two macros, then call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`platform.c:57-63`) | Assigns the two static pointers |

The header's own doc (`configs/ext/tfm_mbedcrypto_config_profile_medium.h`) describes the same two options. The index does not hold a definition site for the two `*_MACRO` symbols, which is expected because they are user-supplied.

## What the library does with the facility

**Built-in allocator, `memory_buffer_alloc`.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`):
- Zeroes the heap context and, if `MBEDTLS_THREADING_C` is on, initializes a mutex.
- Calls `mbedtls_platform_set_calloc_free(...)`, pointing at `buffer_alloc_calloc_mutexed` (which locks, calls `buffer_alloc_calloc`, unlocks) or plain `buffer_alloc_calloc`, plus the matching free.
- Carves its first block out of `buf`, aligned to `MBEDTLS_MEMORY_ALIGN_MULTIPLE`.

So the library never calls libc's allocator when this is in use. It is also the only in-tree consumer of the runtime setter.

**Points to check:**
- The heap is a process-global, so there is one per process.
- Init does not report failure. If `len` is too small, it returns early after the pointers are already set, and `buffer_alloc_calloc` then returns NULL.

## Defaults and a discrepancy

- With `MBEDTLS_PLATFORM_MEMORY` on and no std functions, `platform.c:24-33` falls back to `platform_calloc_uninit` (`platform.c:25-30`), which always returns NULL. Allocation fails until a real allocator is set.
- The index reports `MBEDTLS_PLATFORM_STD_CALLOC` default as **off** with `origin: heuristic`. The repository's own documentation says the default is the system `calloc()`/`free()`. I could not reconcile these from the index. Check `include/mbedtls/mbedtls_config.h:4124` directly before relying on either.