## Short answer

Every library allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, never directly through `malloc`/`calloc`/`free`. What those two names resolve to depends on the build configuration. Without `MBEDTLS_PLATFORM_MEMORY` they are plain `calloc` and `free`. With it, they are either compile-time macros or runtime-swappable function pointers.

## What gets called

| Configuration | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default, `mbedtls_config.h:208` commented out) | `calloc` / `free` directly (`include/mbedtls/platform.h:163-167`) |
| On, plus `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Your macros, expanded inline. No runtime setter is compiled in (`platform.h:139-144`, `platform.c:20-22`). |
| On, neither macro set | Two real functions in `library/platform.c:47-55`. They call through static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`, which start as `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. |

`MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` default to `calloc` and `free` (`platform.h:83-88`). If the user defines them, the user's versions are used. If they are left undefined, the library substitutes `platform_calloc_uninit`, which returns NULL, and `platform_free_uninit`, which does nothing (`platform.c:24-42`). So an unconfigured runtime build fails every allocation cleanly rather than crashing.

Note the constraints in `check_config.h:548-577`. The two macros must be defined together, and neither can be combined with the `STD_*` overrides. Both also require `MBEDTLS_PLATFORM_C` and `MBEDTLS_PLATFORM_MEMORY`.

## How a project substitutes its own allocator

**Option A: compile time.** Enable `MBEDTLS_PLATFORM_C` and `MBEDTLS_PLATFORM_MEMORY`, then define both macros, for example in `mbedtls_config.h` or with `-D`:

```c
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free
```

This is zero-overhead, but the allocator is fixed at build time.

**Option B: runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` without the macros, then call the setter before any other library call:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

The setter (`platform.c:57-63`) only stores the two pointers. It does no validation and does not migrate existing allocations. Any block allocated under the old allocator must be freed by that same allocator, so the switch has to happen before the library allocates anything.

Either way, the substitute must follow `calloc` and `free` semantics. The library calls `mbedtls_calloc(n, size)` with a zero-fill expectation and checks the result for NULL.

## What the library does with the facility

- **Uniform use.** Nearly every module allocates and frees through `mbedtls_calloc` and `mbedtls_free`. Examples include `pem.c`, `x509.c`, `ecp.c`, `ssl_cache.c`, `psa_crypto_slot_management.c`, and `md.c`. Each allocation is checked for NULL.
- **Zeroize before free.** Key-bearing structures are wiped with `mbedtls_platform_zeroize` before the free call, as in `memory_buffer_alloc.c:607`.
- **Built-in replacement.** `library/memory_buffer_alloc.c` is the one allocator the library ships that uses the runtime facility. `mbedtls_memory_buffer_alloc_init()` (`memory_buffer_alloc.c:566-600`) carves allocations out of a caller-supplied static buffer. It then calls `mbedtls_platform_set_calloc_free()` to install its own `buffer_alloc_calloc` and `buffer_alloc_free`. When `MBEDTLS_THREADING_C` is on, it installs mutex-wrapped versions instead (`:541-563`). `mbedtls_memory_buffer_alloc_free()` (`:602`) releases the mutex and zeroizes the heap state, but it does not restore the standard allocator.
- **Process-global.** Because the setter writes to global pointers, the substitute applies process-wide. Only one heap can be active at a time.

## Caveats

- **Raw `free` in the backtrace path.** `memory_buffer_alloc.c:404` calls libc `free(hdr->trace)` directly. That is correct only because `backtrace_symbols` allocates with libc `malloc`. It bypasses the substitutable facility, and it only compiles under `MBEDTLS_MEMORY_BACKTRACE`.
- **Mixing allocators.** Freeing a library-owned pointer with the project's own `free`, or with the wrong heap, corrupts the heap. The library documents this in its API comments, for example `asn1.h:379-380` and `x509.c:494`.
- **Unconfigured runtime builds fail silently.** With neither macros nor `STD_*` defined, every allocation returns NULL, and the library reports allocation failures to the caller.

I read the source and did not build or run anything, so the claims above rest on static reading.