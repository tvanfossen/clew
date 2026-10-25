## What gets called

Mbed TLS never calls `malloc` directly. Every allocation goes through `mbedtls_calloc(n, size)` and every release through `mbedtls_free(ptr)`. About 364 call sites across 50 files in `library/` use these two names. What they resolve to depends on build configuration, and there are three cases:

```
MBEDTLS_PLATFORM_MEMORY undefined (default)
    mbedtls_calloc  ->  #define  ->  calloc        (libc, resolved at compile time)
    mbedtls_free    ->  #define  ->  free

MBEDTLS_PLATFORM_MEMORY + CALLOC_MACRO + FREE_MACRO   (compile-time substitution)
    mbedtls_calloc  ->  #define  ->  MBEDTLS_PLATFORM_CALLOC_MACRO   (your function)
    mbedtls_free    ->  #define  ->  MBEDTLS_PLATFORM_FREE_MACRO

MBEDTLS_PLATFORM_MEMORY, no macros   (runtime substitution)
    mbedtls_calloc  ->  library/platform.c function  ->  function pointer
    mbedtls_free    ->  library/platform.c function  ->  function pointer
```

- **Default:** `include/mbedtls/platform.h:163-168` maps the names straight to libc, so there is no indirection at all.
- **Runtime hook:** `platform.c:44-54` defines the two wrappers, which call through static function pointers. Those pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE`. If the project has not defined those, `platform.c:24-42` substitutes stubs: calloc returns NULL and free does nothing. The header comment at `mbedtls_config.h:172-197` describes this chain.

## How a project substitutes its own allocator

**Option A: compile time (no runtime cost, no setter).** In the config, or in a `MBEDTLS_USER_CONFIG_FILE`:

```c
#define MBEDTLS_PLATFORM_C                 /* required */
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc   /* void *(size_t, size_t) */
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free     /* void (void *) */
```

Both macros must be set together. `check_config.h:558-573` enforces that, and `platform.c:20-22` drops the runtime setter entirely.

**Option B: runtime.** Define only `MBEDTLS_PLATFORM_MEMORY` (optionally with `MBEDTLS_PLATFORM_STD_CALLOC/FREE` for a non-libc default), then call this before any Mbed TLS allocation:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);   /* always returns 0 */
```

The setter in `platform.c:57-63` overwrites both pointers without validation. It does not check that you passed a pair, and it does not guard against being called mid-operation.

Rules the project must follow:
- Set the allocator before the first Mbed TLS call.
- Use the same allocator for `calloc` and `free`. Freeing with a different pool is undefined behaviour.
- `free` must accept NULL. The config docs say a non-null argument is always one that was previously returned by the calloc function (`mbedtls_config.h:4129-4131`).
- If Mbed TLS runs across threads, the allocator must be thread-safe. `memory_buffer_alloc.h:44-47` says this explicitly.

## What the library does with the facility

- **Every allocation is checked.** Callers test the result for NULL and return an error, which the ChangeLog records as a bug-fix pattern (`ChangeLog:173`). The library treats `mbedtls_calloc` as fallible.
- **It has no direct allocator calls of its own.** A grep of `library/` for raw `malloc`/`calloc`/`free` finds only comments, plus one `free(hdr->trace)` inside the built-in allocator (`memory_buffer_alloc.c:404`).
- **Built-in pool allocator.** `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is one consumer of the facility. `memory_buffer_alloc.h:44-47` says its `mbedtls_memory_buffer_alloc_init()` points the global `mbedtls_calloc` / `mbedtls_free` at its own functions. Those serve memory from a caller-supplied buffer and never call libc. `check_config.h:426-428` requires `MBEDTLS_PLATFORM_MEMORY` for it. In this repo it is used by the test programs (`ssl_server2`, `ssl_client2`, `benchmark`, `selftest`), not by the core library itself.

## Not verified

- I did not confirm the exact file where `MBEDTLS_PLATFORM_STD_CALLOC = calloc` is defined when `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is off. The config comment describes it, but I did not trace the define.
- I did not build or run anything, so the substitution options are checked against the source and docs, not a compile.