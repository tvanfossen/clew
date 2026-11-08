## What gets called

Every allocation inside the library goes through `mbedtls_calloc()` / `mbedtls_free()`, never libc directly. Which function that resolves to depends on configuration:

```
library code: mbedtls_calloc(n, sz)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY off (default)
        │     → #define mbedtls_calloc calloc          (include/mbedtls/platform.h:166)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY on, CALLOC_MACRO + FREE_MACRO both defined
        │     → #define mbedtls_calloc MBEDTLS_PLATFORM_CALLOC_MACRO   (platform.h:143)
        │
        └─ MBEDTLS_PLATFORM_MEMORY on, no macros
              → real function library/platform.c:47
                  → (*mbedtls_calloc_func)(n, size)   runtime function pointer
```

In the third case the pointers start as `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` (platform.c:24–45). If those are not defined, they become stubs: calloc returns NULL and free does nothing. So a build with `MBEDTLS_PLATFORM_MEMORY` but no standard functions allocates nothing unless the project installs its own. The config header documents this precedence (mbedtls_config.h:160–190).

## How a project substitutes its allocator

Two options, and the compile-time one wins if both are present (platform.c:16–19).

**Compile time.** Enable `MBEDTLS_PLATFORM_MEMORY` and define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config, e.g. `#define MBEDTLS_PLATFORM_CALLOC_MACRO my_calloc`. Both must be set together. The library then calls your functions directly, with no indirection.

**Runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` without the macros. Then call once, before any library allocation:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);   // platform.c:57
```

This just assigns the two static pointers. Nothing checks that you did it. Any allocation before the call goes to the default stub.

## What the library does with the facility

The library itself ships one allocator to plug into it: `mbedtls_memory_buffer_alloc_init(buf, len)` (memory_buffer_alloc.c:566). It:

1. Zeroes its global `heap` context and initialises a mutex when `MBEDTLS_THREADING_C` is on.
2. Calls `mbedtls_platform_set_calloc_free()` with its own wrappers: `buffer_alloc_calloc_mutexed` / `buffer_alloc_free_mutexed` when threading is on, otherwise the unlocked pair.
3. Carves its heap out of the caller's buffer, aligning it first.

So the library's own heap is just one more substitute, installed through the same runtime hook. Points to keep in mind:

- **Global state.** There is one `heap` per process, and each init call overwrites the pointers. Two buffers cannot be active at once.
- **Mutexing.** Only the threaded variant locks around alloc and free, and a failed lock returns NULL from calloc. A free that cannot take the lock is silently dropped, which the code comments call "losing memory" rather than corrupting the heap.
- **A libc leak in one configuration.** With `MBEDTLS_MEMORY_BACKTRACE`, `buffer_alloc_free` calls libc `free(hdr->trace)` directly (memory_buffer_alloc.c:404). Its trace buffer is not allocated through the substitutable hook.
- **Library-wide use.** A grep of `library/*.c` for direct `calloc(` or `free(` found only comments and that trace call. Calls such as `ecp_mul_comb`, `aes_ctx_alloc` and `asn1_get_sequence_of_cb` all go through `mbedtls_calloc`. The index shows 147 call sites of `mbedtls_calloc`.

I did not check the `programs/` or `tests/` trees for direct libc use, and I did not check the ext/TF-M configs beyond their comments. The claim that the library never calls libc allocators is limited to `library/`.