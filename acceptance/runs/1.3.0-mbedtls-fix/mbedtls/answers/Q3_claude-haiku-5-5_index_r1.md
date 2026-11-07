**Short answer:** every allocation in the library goes through `mbedtls_calloc()` / `mbedtls_free()`. What those resolve to depends on three config symbols. A project substitutes its allocator either at compile time (macros) or at runtime (a setter function).

## What gets called

Resolution is decided in `include/mbedtls/platform.h` and `library/platform.c`:

| Config | `mbedtls_calloc` / `mbedtls_free` become |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | Plain `calloc` / `free` (`platform.h:163-167`). No indirection. |
| `MBEDTLS_PLATFORM_MEMORY` on, plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Those macros, expanded at compile time (`platform.h:139-145`). The runtime setter is not compiled. |
| `MBEDTLS_PLATFORM_MEMORY` on, no macros | Real functions in `platform.c:47-55` that call through two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func` (`platform.c:44-45`). |

The pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE`. Those default to `calloc` / `free` (`platform.h:83-88`). The `NO_STD_FUNCTIONS` guard I saw around `platform.h:57` is the only one I checked, so I have not confirmed that it is the only condition that changes this default. If the standard functions are not available, the default is the `platform_calloc_uninit` stub in `platform.c:25-30`, which always returns NULL. Until a real allocator is installed, every allocation fails.

## How a project substitutes its allocator

Option A, compile time (no runtime pointer, no setter):

```c
/* mbedtls_user_config.h, or any config header included by the build */
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc   /* void *(size_t, size_t) */
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free     /* void (void *)         */
```

The two macros must be defined together. The comment at `platform.c:16-19` says the compile-time macros take precedence. In this mode `mbedtls_platform_set_calloc_free` is not declared, so calling it is a compile error.

Option B, runtime (only `MBEDTLS_PLATFORM_MEMORY` defined):

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);   /* before any mbedtls call */
```

The library never calls the setter itself. If nothing calls it, the default stub returns NULL.

Your `calloc` must zero the memory it returns. The config documentation (`mbedtls_config.h:4113-4116`) requires this.

Option C: keep the runtime setter, but point the default at a different function with `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE`.

## What the library does with it

- **Every allocation funnels through the wrappers.** The index's AST-resolved callers of `mbedtls_calloc` include the cipher, PK, ECP, X.509, PSA, bignum and SSL modules. A grep for bare `malloc(`, `calloc(` and `free(` in `library/` found none outside comments, so the substitution covers the library.
- **The library itself is the only consumer of the setter.** `library/memory_buffer_alloc.c:566-576`: `mbedtls_memory_buffer_alloc_init(buf, len)` calls `mbedtls_platform_set_calloc_free(...)` with its own `buffer_alloc_calloc` and `buffer_alloc_free`. Using the built-in buffer allocator therefore silently replaces the global allocator. The mutex-wrapped variants are used when `MBEDTLS_THREADING_C` is on.
- **Teardown does not restore the previous allocator.** `mbedtls_memory_buffer_alloc_free()` (`memory_buffer_alloc.c:602-608`) only destroys the mutex and zeroes the heap context. The function pointers still point at the buffer allocator's functions, which now operate on zeroed state. I have not checked whether this is intended. If the heap is torn down and the library keeps allocating, the failure will come from the buffer allocator, not from the standard allocator.