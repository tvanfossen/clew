**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, which dispatch through two static function pointers in `library/platform.c`. By default those pointers point at the C standard library, and a project can replace them.

**What gets called**

```
library code (ssl, x509, pk, cipher_wrap, psa ...)
  └─ mbedtls_calloc(n, size)      library/platform.c:47
       └─ (*mbedtls_calloc_func)(n, size)
            default: MBEDTLS_PLATFORM_STD_CALLOC  (libc calloc)
  └─ mbedtls_free(p)              library/platform.c:52
       └─ (*mbedtls_free_func)(p)
            default: MBEDTLS_PLATFORM_STD_FREE    (libc free)
```

- `mbedtls_calloc_func` and `mbedtls_free_func` are `static` in `platform.c` (lines 44–45), initialised to the standard functions.
- The index shows 147 callers of `mbedtls_calloc`, so the facade is used broadly. The reply capped the list at 25.
- When `MBEDTLS_PLATFORM_STD_CALLOC` is not defined, `platform.c` (around lines 24–33) falls back to a static `platform_calloc_uninit` that always returns `NULL`. So a build with no allocator fails allocations rather than linking to libc.
- `platform.h` also defines the `mbedtls_calloc`/`mbedtls_free` macros (lines 143–144 and 166–167). Their expansions depend on `MBEDTLS_PLATFORM_CALLOC_MACRO`/`_FREE_MACRO` and `MBEDTLS_PLATFORM_MEMORY`. The index does not show the `#if` arms clearly enough for me to say which expansion wins in each configuration, so read `platform.h` before relying on the macro path.

**How a project substitutes its allocator**

Two routes, both shown in the index:

1. **Runtime, global:** call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57`). It assigns the two pointers and returns 0. It has no locking and no error path, so call it before any other mbedtls use.
2. **Compile time:** enable `MBEDTLS_PLATFORM_MEMORY` and supply `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` in the user config. Overriding `MBEDTLS_PLATFORM_STD_CALLOC` changes the default pointer value. The test fixture `tests/configs/user-config-malloc-0-null.h` does this with a `custom_calloc`. The index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO` or `_FREE_MACRO`, so the project's own config must provide them.

**What the library does with the facility**

- **Its own allocator is a client of it.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566`) does not call libc. It calls `mbedtls_platform_set_calloc_free` with its own `buffer_alloc_calloc_mutexed` (or unlocked `buffer_alloc_calloc` if `MBEDTLS_THREADING_C` is off), then carves the caller's buffer into a heap.
- **That call is process-global.** It replaces the pointers for the whole process, not just for one context.
- **Edge case:** the pointer swap happens before the `len < sizeof(memory_header) + …` check. An undersized buffer therefore leaves the replacement allocator installed with no usable heap, and the function returns `void`, so the caller gets no error.
- **No locking on the pointers.** The pointers are plain statics written without synchronisation. The index shows a `pthread` entry point (`handle_ssl_connection`, medium confidence) that reaches `mbedtls_free`. If you swap the allocator while threads are running, you own that race.