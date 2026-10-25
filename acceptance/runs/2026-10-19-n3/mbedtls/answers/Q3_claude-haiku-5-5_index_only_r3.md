**Short answer:** mbedtls never calls `calloc`/`free` directly. Every library allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, which dispatch through two global function pointers. Those pointers default to the C library, or can be redirected at build time or at runtime.

**The call chain**

```
library code
  → mbedtls_calloc(n, size)            (macro, include/mbedtls/platform.h:144)
      → MBEDTLS_PLATFORM_CALLOC_MACRO  (if the integrator defines it, used directly)
      or → mbedtls_calloc()            (library/platform.c:47)
             → (*mbedtls_calloc_func)(n, size)
                 default: MBEDTLS_PLATFORM_STD_CALLOC (calloc)
                 or platform_calloc_uninit (platform.c:25), which returns NULL
```

`mbedtls_free()` (platform.c:52) mirrors this through `mbedtls_free_func`.

If `MBEDTLS_PLATFORM_MEMORY` is not defined, the `mbedtls_calloc` and `mbedtls_free` macros at platform.h:167 and 166 expand straight to libc `calloc` and `free`. The index shows that block gated on `MBEDTLS_PLATFORM_MEMORY`. The index's caller lists show nearly all library sites (AES/ECP/MPI/SSL/X.509/PSA code) using the wrapper names.

**How a project substitutes its own allocator**

There are three ways, all of which the index shows evidence for:

1. **Compile-time function names.** Define `MBEDTLS_PLATFORM_MEMORY`, then `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` (or the `_MACRO` variants). `tests/configs/user-config-malloc-0-null.h` does this: it sets `MBEDTLS_PLATFORM_MEMORY` at line 20 and `MBEDTLS_PLATFORM_STD_CALLOC` to `custom_calloc` at line 21.
2. **Compile-time macros.** Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to name your own functions. The index has no definition site for these in the shipped headers, so they must come from the user's config.
3. **Runtime.** Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (platform.c:57). It simply assigns the two pointers. Requires `MBEDTLS_PLATFORM_C`, which is on by default.

Caveat: I did not read the header bodies themselves, so the exact `#if` expressions are inferred from the index's gate records. Confirm against `include/mbedtls/platform.h` and `library/platform.c` before relying on the precise conditions.

**What the library does with the facility itself**

The library ships one allocator of its own, `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566`). It:

- Zeroes a static global `heap` context.
- Initializes its mutex if `MBEDTLS_THREADING_C` is set.
- Calls `mbedtls_platform_set_calloc_free()` to install `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` (or the unmutexed pair). This is the library using its own public setter to swap itself in.
- Aligns the caller's buffer, writes magic-tagged block headers, and serves all allocations from that buffer, so `calloc`/`free` are never called.

So the hook is used in two ways: by the integrator, who supplies a heap or a custom allocator, and by the library's own memory-buffer allocator, which is simply the one built-in implementation.