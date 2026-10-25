**Short answer:** library code never calls `calloc`/`free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, and what those names resolve to depends on the build configuration.

## What gets called

```
library code ──► mbedtls_calloc(n, sz)
                    │
     ┌──────────────┼───────────────────────────────┐
     │              │                               │
 !MBEDTLS_PLATFORM_MEMORY          MEMORY + both *_MACRO         MEMORY, no macros
 (platform.h:166)                  (platform.h:143)              (platform.h:148, platform.c:47)
     │                                  │                               │
  #define → calloc                 #define → your fn              mbedtls_calloc_func(n, sz)
                                                                  (function pointer, default
                                                                   MBEDTLS_PLATFORM_STD_CALLOC)
```

- **Default build** (`MBEDTLS_PLATFORM_MEMORY` undefined): `platform.h:166-167` makes `mbedtls_calloc` a macro for `calloc` and `mbedtls_free` a macro for `free`. There is no indirection.
- **Compile-time hook**: with `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`, the names become macros for your functions (`platform.h:143-144`). Nothing is stored at runtime.
- **Runtime hook** (`library/platform.c:44-62`): with `MBEDTLS_PLATFORM_MEMORY` and no macros, `mbedtls_calloc` and `mbedtls_free` are real functions that call through two static function pointers. Those start at `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`.
- **Default for those pointers**: `calloc`/`free` if the standard functions are available. Under `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`, the fallback is a stub (`platform_calloc_uninit`) that always returns `NULL`. So a project that forgets to install an allocator gets allocation failures, not a link error.

## How a project substitutes its allocator

1. In `mbedtls_config.h` or via `-D`, enable `MBEDTLS_PLATFORM_MEMORY`. `MBEDTLS_PLATFORM_C` must also be on (`check_config.h:576`).
2. Pick one:
   - **Compile time:** define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` together. Both must be set or neither.
   - **Runtime:** call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any Mbed TLS allocation. The setter (`platform.c:57-63`) does no locking and no NULL checks, and always returns 0.
   - **Change the default pointers:** define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` to your functions. These are only the initial values, so the runtime setter can still replace them.
3. Don't define `CALLOC_MACRO` and `STD_CALLOC` together (`check_config.h:568`).

The runtime setter is process-wide. The library doesn't record which allocator produced a block, so swapping allocators while blocks are still live will free memory into the wrong allocator.

## What the library does with the facility itself

`library/memory_buffer_alloc.c` is a built-in first-fit heap over a buffer the caller supplies. `mbedtls_memory_buffer_alloc_init()` (around line 570) calls `mbedtls_platform_set_calloc_free()` unconditionally:

- With `MBEDTLS_THREADING_C`, it installs `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed`, which wrap the heap in `heap.mutex`.
- Without threading, it installs the unlocked versions.

Two consequences:

- **It overwrites any allocator installed earlier.** A project that set its own allocator and then calls `mbedtls_memory_buffer_alloc_init()` silently loses it. Set the allocator after the heap init, or don't mix the two.
- **The mutexed free fails safe.** If it can't take the lock, it skips the free rather than corrupting the heap, which leaks memory instead.

Other library uses of the hook:

- `library/platform_util.c:145` (`mbedtls_zeroize_and_free`) frees through `mbedtls_free`, so secure frees also go through the substituted allocator.
- The only raw libc `free` in `library/` is `memory_buffer_alloc.c:404`, which frees the `backtrace_symbols()` output in the `MBEDTLS_MEMORY_BACKTRACE` debug path. That output is not a library allocation, so it correctly bypasses the hook.

I didn't build or run anything; this is from reading the sources.