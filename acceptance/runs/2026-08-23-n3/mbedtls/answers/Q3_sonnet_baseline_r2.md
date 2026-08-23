Grounded in what's actually in this checkout (`library/platform.c`, `include/mbedtls/platform.h`, `include/mbedtls/mbedtls_config.h`, `library/memory_buffer_alloc.c`):

## What actually gets called

Every dynamic allocation in the library goes through two library-defined functions, `mbedtls_calloc()` / `mbedtls_free()` — never a bare `calloc`/`free` call sprinkled through the codebase. 48 files under `library/` call `mbedtls_calloc(`. Whether those two names resolve to the libc functions directly, or to indirection through function pointers, is decided entirely by preprocessor logic in `include/mbedtls/platform.h`, gated by the `MBEDTLS_PLATFORM_MEMORY` config option (`mbedtls_config.h:155-208`, off by default):

- **`MBEDTLS_PLATFORM_MEMORY` undefined (the default):** `platform.h` just does `#define mbedtls_calloc calloc` / `#define mbedtls_free free`. Zero indirection — it compiles straight down to the system allocator.

- **`MBEDTLS_PLATFORM_MEMORY` defined, no `MBEDTLS_PLATFORM_{CALLOC,FREE}_MACRO`:** `platform.h` declares real functions `mbedtls_calloc`/`mbedtls_free`, implemented in `library/platform.c:44-62` as thin wrappers around two static function pointers, `mbedtls_calloc_func`/`mbedtls_free_func`, initialized to `MBEDTLS_PLATFORM_STD_CALLOC`/`MBEDTLS_PLATFORM_STD_FREE` (which default to plain `calloc`/`free` per `mbedtls_config.h:83-88`). This is the runtime-swap path.

- **`MBEDTLS_PLATFORM_MEMORY` defined AND `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO` both defined:** `platform.h:141-144` `#undef`s and redefines `mbedtls_calloc`/`mbedtls_free` as those macros directly — a compile-time swap, no function pointer, no runtime hook exposed.

## How a project substitutes its own allocator

Two supported mechanisms, mutually exclusive:

1. **Runtime substitution.** Enable `MBEDTLS_PLATFORM_MEMORY` in `mbedtls_config.h`, leave the `*_MACRO` options unset, then at startup call:
   ```c
   int mbedtls_platform_set_calloc_free(void *(*calloc_func)(size_t, size_t),
                                        void (*free_func)(void *));
   ```
   (declared `platform.h:160-161`, implemented `platform.c:57-62`) — this just overwrites `mbedtls_calloc_func`/`mbedtls_free_func`. Every subsequent library allocation goes through the caller-supplied functions. Useful when the allocator choice is a runtime decision (e.g. different pool per test, or picking an allocator only known after `main()` starts).

2. **Compile-time substitution.** Enable `MBEDTLS_PLATFORM_MEMORY` and also define `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO` to name your own functions. `mbedtls_calloc`/`mbedtls_free` become macros expanding straight to those names — no indirection, no runtime hook, and (per the config comment) you cannot combine this with `MBEDTLS_PLATFORM_STD_CALLOC`/`STD_FREE`.

The config header spells out the resolution order explicitly at `mbedtls_config.h:172-201`, including the edge case that an uninitialized `MBEDTLS_PLATFORM_STD_CALLOC` under `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` falls back to an `uninitialized_calloc` stub that always fails (fail-closed, not silently falling back to libc).

## What the library itself does with the facility

mbedTLS ships its own consumer of this exact hook: `library/memory_buffer_alloc.c`, gated by `MBEDTLS_MEMORY_BUFFER_ALLOC_C` (requires `MBEDTLS_PLATFORM_MEMORY`, per `mbedtls_config.h:3062-3076`). This is a static/stack-buffer sub-allocator for memory-constrained or embedded targets with no heap. It implements `buffer_alloc_calloc`/`buffer_alloc_free` (and mutex-guarded variants `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` when threading is enabled) that carve allocations out of a caller-supplied fixed buffer instead of calling libc. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-575`) registers these via the very same `mbedtls_platform_set_calloc_free()` runtime hook described above — i.e. mbedTLS's own bundled allocator is not special-cased internally; it's just the reference implementation of "substitute your own allocator," wired in through the public API a project would use for the same purpose. This is the canonical embedded-systems use case: a target with `malloc`/`free` unavailable or undesirable (fragmentation risk, no heap) points the whole library at one fixed arena instead.
