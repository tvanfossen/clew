## Short answer

Library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, which are thin wrappers that forward through two static function pointers in `library/platform.c`. A project swaps the allocator by installing its own function pointers at runtime, or by pointing the macros at its own symbols at compile time.

## The call chain

```
library code (e.g. aes_ctx_alloc, mbedtls_md_setup, ssl_*)
        │  mbedtls_calloc(n, size)          [macro, platform.h]
        ▼
mbedtls_calloc()  — library/platform.c:47
        │  (*mbedtls_calloc_func)(n, size)  [static fn ptr, platform.c:44]
        ▼
the installed allocator (libc calloc, your allocator, or the buffer allocator)
```

`mbedtls_free()` at `library/platform.c:52` follows the same pattern through `mbedtls_free_func` (`platform.c:45`).

The function pointers are initialised to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. The index shows `MBEDTLS_PLATFORM_STD_CALLOC` is off by default (`mbedtls_config.h:4124`). Where it is off, the fallback `platform_calloc_uninit` (`platform.c:25`) simply returns `NULL`, so allocation fails until something is installed. I did not query the free-side default body, so treat the exact fallback behaviour on that side as unverified.

## How a project substitutes its allocator

There are three routes. The index shows all three:

1. **Runtime, via `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)`** (`platform.c:57`). It assigns the two static pointers and returns 0. It is the only setter, and it has no failure path. Call it before any library allocation.
2. **Compile time, via the `MBEDTLS_PLATFORM_MEMORY` gate in `include/mbedtls/platform.h:138–168`.** Inside it, the `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` options (both default off in `mbedtls_config.h:4150–4151`) redirect the `mbedtls_calloc`/`mbedtls_free` macros to your own symbols. The test config `tests/configs/user-config-malloc-0-null.h` uses this route, mapping `MBEDTLS_PLATFORM_STD_CALLOC` to a `custom_calloc`.
3. **Shipped alternative, `mbedtls_memory_buffer_alloc_init(buf, len)`** (`library/memory_buffer_alloc.c:566`). It serves allocations from a caller-supplied static buffer. It calls `mbedtls_platform_set_calloc_free` itself, choosing `buffer_alloc_calloc_mutexed` when `MBEDTLS_THREADING_C` is set, otherwise `buffer_alloc_calloc`. It also initialises a mutex and lays out a header-linked free list inside the buffer.

A project's minimal integration is therefore:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);  // before any mbedtls call
```

or, for a static-memory build, `mbedtls_memory_buffer_alloc_init(pool, sizeof pool);` followed by the normal library calls.

## What the library does with the facility

- **Allocation sites use the wrappers everywhere.** The index shows `mbedtls_calloc` referenced by the context constructors in `cipher_wrap.c` (AES, ARIA, DES, GCM, CCM, ChaCha20 and others), by the ECP/MPI code, by the PK and X.509 parsers, by the SSL code, and by PSA key handling. `mbedtls_free` mirrors this on the destructor paths.
- **The `ALLOC` macro in `library/md.c`** is a typical example. It calls `mbedtls_calloc(1, sizeof(...))`, returns `MBEDTLS_ERR_MD_ALLOC_FAILED` on NULL, then runs the type's `_init`.
- **Overflow checking happens inside the buffer allocator**, not in the wrapper. `buffer_alloc_calloc` rejects `n*size` overflow and oversize requests before searching the free list.
- **The buffer allocator also zeroes, guards and debugs its own heap**: it uses magic-number headers, optional backtraces (`MBEDTLS_MEMORY_BACKTRACE`) and optional debug output (`MBEDTLS_MEMORY_DEBUG`). It calls `mbedtls_exit(1)` if it finds a block on the free list that is already allocated.

## Caveats

- The index does not show where the library *reads* the free pointer on zeroize-and-free paths beyond the listed callers. `mbedtls_zeroize_and_free` is a caller of `mbedtls_free`, so the sensitive-buffer path goes through the same hook.
- The `KRML_HOST_CALLOC`/`MALLOC` macros in `3rdparty/everest` are the Everest/Kremlin code's own allocator hooks. They are separate from the mbedtls facility.