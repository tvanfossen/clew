## What actually gets called

The library never calls `malloc`, `calloc` or `free` directly. A grep of `library/` finds only comments and one debug-only `free()` in `memory_buffer_alloc.c:404`. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, which are called from cipher contexts, the ASN.1/X.509 parsers, PK, PSA, SSL and bignum code.

What those two names resolve to depends on the build config, in `include/mbedtls/platform.h`:

```
MBEDTLS_PLATFORM_MEMORY off (default)
  mbedtls_calloc -> calloc          (macro, platform.h:163-167)
  mbedtls_free   -> free

MBEDTLS_PLATFORM_MEMORY on, + both CALLOC_MACRO and FREE_MACRO
  mbedtls_calloc -> your macro      (compile-time, platform.h:139-144)
  mbedtls_free   -> your macro

MBEDTLS_PLATFORM_MEMORY on, no macros
  mbedtls_calloc() -> (*mbedtls_calloc_func)()   (platform.c:47-50)
  mbedtls_free()   -> (*mbedtls_free_func)()     (platform.c:52-55)
      pointers default to MBEDTLS_PLATFORM_STD_CALLOC/FREE (calloc/free),
      or to "always fail" stubs if those are undefined (platform.c:24-45)
```

## How a project substitutes its allocator

Two routes, both requiring `MBEDTLS_PLATFORM_C` (platform.c:10):

1. **Compile time (no runtime indirection).** In the project's user config, define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. `tests/configs/user-config-malloc-0-null.h` is a working example. When both macros are set, the runtime setter is compiled out.

2. **Runtime.** Define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any library allocation. The setter is declared only in the `MBEDTLS_PLATFORM_MEMORY` branch (platform.h:160), so it does not exist in the other configurations.

Requirements the config header places on the replacements (mbedtls_config.h:4113-4133):
- `calloc` must zero the memory.
- It may return NULL on failure.
- For a zero size it may return NULL or a valid pointer.
- `free(NULL)` must be a no-op.

Caveat from the code: `mbedtls_platform_set_calloc_free` always returns 0 (platform.c:62) and does not check whether memory is already outstanding. Swapping allocators after the library has allocated will leave blocks that are later freed by the wrong function. Do the swap during init.

## What the library does with the facility

The library uses the same hook itself. `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) is a built-in heap:

- It zeroes a static `heap` context and calls `mbedtls_platform_set_calloc_free()` with `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` when `MBEDTLS_THREADING_C` is on, or the unmutexed pair otherwise.
- It carves all allocations out of the caller's buffer. `buffer_alloc_calloc` checks for `n*size` overflow, rounds to `MBEDTLS_MEMORY_ALIGN_MULTIPLE`, and does a first-fit search of the free list.
- Init failures are silent. If `len` is too small, init returns after installing the function pointers but with `heap.buf` NULL, and every later `calloc` returns NULL.
- The heap is a single process-wide static, so there is one buffer heap per process.

The doc comment on that init function says it "does not call calloc() and free()", which matches the code. `benchmark.c` and the library's own self-test use it, so a constrained target can get a fixed-memory heap without writing an allocator. The same runtime hook is what a project would use for its own allocator.