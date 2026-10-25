## What `mbedtls_calloc` and `mbedtls_free` resolve to

Library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()` (about 169 and 189 call sites under `library/`). What those names resolve to depends on the build configuration, and `include/mbedtls/platform.h:138-168` has three cases:

| Configuration | `mbedtls_calloc` / `mbedtls_free` become |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default, `mbedtls_config.h:208` is commented out) | Macros for libc `calloc` / `free` |
| `MBEDTLS_PLATFORM_MEMORY` on, plus `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Macros for your compile-time functions |
| `MBEDTLS_PLATFORM_MEMORY` on, no macros | Real functions in `library/platform.c:47-55` that dispatch through function pointers |

The third case is the runtime-substitution path. `platform.c:44-45` holds two static pointers, `mbedtls_calloc_func` and `mbedtls_free_func`, initialized to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. Each wrapper just forwards through its pointer.

Those defaults come from `platform.h:83-88`, which map them to libc `calloc`/`free` unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set. If a user has defined `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` and not supplied an allocator, `platform.c:24-42` substitutes stubs: calloc returns NULL and free does nothing. So an uninitialized allocator fails closed rather than crashing.

## How a project substitutes its own allocator

**Compile time.** Define both macros in the config or build flags:

```c
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free
```

`check_config.h:558-573` requires both macros to be defined together, and `MBEDTLS_PLATFORM_C` must also be enabled. The macros are substituted at every call site, so no runtime dispatch occurs.

**Runtime.** Define only `MBEDTLS_PLATFORM_MEMORY`, then call the setter before any other library call:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

This is a single global pointer swap in `platform.c:57-63`. The setter does no locking and no validation, and it always returns 0. The pair must be set consistently and before any allocation, because memory from one allocator must be freed by the same one. Optionally, `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` can be defined to change the initial defaults.

## What the library does with the facility

**1. Its own allocator, `memory_buffer_alloc`.** This is the in-library use of the hook. `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c`, around line 565-575) calls `mbedtls_platform_set_calloc_free()` with its own functions. These serve allocations from a caller-supplied static buffer using a first-fit free list with headers. Without `MBEDTLS_THREADING_C` it installs `buffer_alloc_calloc`/`buffer_alloc_free` directly. With threading it installs `*_mutexed` wrappers that take `heap.mutex` around each call. This requires `MBEDTLS_MEMORY_BUFFER_ALLOC_C` and `MBEDTLS_PLATFORM_MEMORY`, as noted at `mbedtls_config.h:3063-3072`. It is the only place in `library/` that calls the setter.

**2. Zeroize-then-free.** `library/platform_util.c:140-146` defines `mbedtls_zeroize_and_free(buf, len)`, which zeroes the buffer with `mbedtls_platform_zeroize()` and then calls `mbedtls_free()`. It is used at 26 sites under `library/`, so secret material is wiped before it goes back to whatever allocator is installed.

**3. Plain libc calls remaining.** Outside the allocator layer, the only raw `free()` in `library/` is `memory_buffer_alloc.c:404`, which releases a debug trace string in `MBEDTLS_MEMORY_DEBUG` builds. It is not library data and is not routed through the hook.

**Caveat.** Under the runtime-hook setup, the library imposes no thread-safety of its own. Thread-safety depends on the allocator supplied, and the `memory_buffer_alloc` header notes that its functions are thread-safe only when `MBEDTLS_THREADING_C` is enabled.

I did not build the project or run the test suite. The findings come from reading the source and headers.