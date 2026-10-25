## What gets called

Every library allocation goes through one of two names, `mbedtls_calloc` and `mbedtls_free`. What they resolve to depends on the config:

```
library code ── mbedtls_calloc(n, sz) ──┬─ !MBEDTLS_PLATFORM_MEMORY ──────────► libc calloc (macro in platform.h:167)
                                        ├─ MEMORY + CALLOC/FREE_MACRO ──────► your macro, bound at compile time (platform.h:143)
                                        └─ MEMORY, no macros ──────────────► platform.c:49 ──► mbedtls_calloc_func (runtime pointer)
```

- **Default:** `include/mbedtls/platform.h:166-167` defines `mbedtls_free` and `mbedtls_calloc` as plain `free` and `calloc`. Nothing is indirected.
- **Compile-time:** `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` make the names expand straight to your functions. The two macros must be set together (`check_config.h:558-573`).
- **Runtime:** `MBEDTLS_PLATFORM_MEMORY` alone gives you real functions in `library/platform.c:47-63`. They forward through two file-scope function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`. Their defaults are `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. If you don't define those, they're stubs: calloc returns NULL and free does nothing (`platform.c:24-42`).

## How a project substitutes its allocator

Two routes:

1. **Compile time.** In your `mbedtls_config.h` or user config file:
   ```c
   #define MBEDTLS_PLATFORM_MEMORY
   #define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
   #define MBEDTLS_PLATFORM_FREE_MACRO    my_free
   ```
   `tests/configs/user-config-malloc-0-null.h` takes this route. It defines `MBEDTLS_PLATFORM_STD_CALLOC` as a wrapper that returns NULL for zero-size requests.

2. **Runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` without the macros, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other Mbed TLS call. The header describes this in `mbedtls_config.h:160-202`.

The `*_ALT` pattern is the same idea for other platform functions: a config symbol plus assigning the matching `mbedtls_xxx` global (`docs/architecture/alternative-implementations.md`).

## What the library does with the facility

- **It never calls `malloc`, `calloc`, or `free` directly.** A grep of `library/` finds only comments outside the bundled allocator. About 358 call sites across 50 files use `mbedtls_calloc`/`mbedtls_free`, so substituting that pair covers the whole library.
- **It ships an allocator that uses the same hook.** `library/memory_buffer_alloc.c` manages a caller-supplied buffer. Its `mbedtls_memory_buffer_alloc_init()` calls `mbedtls_platform_set_calloc_free()` (lines 571-575). With `MBEDTLS_THREADING_C` it wraps the heap ops in a mutex (lines 540-563). The buffer allocator's `mbedtls_free` aborts with a message on a pointer it does not own (lines 373, 390).

Things to watch, from reading the code (I did not build these):

- **The runtime setter is an unsynchronised global write.** Calling it while another thread is allocating is a race. Install your allocator once, at startup.
- **`mbedtls_memory_buffer_alloc_init()` overrides any allocator you installed earlier.** It calls `set_calloc_free` unconditionally, so a custom allocator set before it is silently replaced.
- **With both macros defined, the runtime setter is not declared.** `platform.h:139-162` only declares it in the non-macro branch, so `memory_buffer_alloc.c` would presumably fail to compile in that combination. I didn't build it to confirm.