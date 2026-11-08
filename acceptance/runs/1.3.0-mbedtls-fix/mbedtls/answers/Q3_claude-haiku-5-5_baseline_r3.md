Short answer: every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those are either the C standard `calloc`/`free` or a project-supplied pair, chosen at build time or at runtime. The library never calls `malloc`, `realloc` or `free` directly.

## What gets called

`include/mbedtls/platform.h:138-168` resolves the names in three ways:

| Configuration | `mbedtls_calloc` / `mbedtls_free` become |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` not defined (default) | macros for `calloc` / `free` (`platform.h:166-167`) |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | macros pointing at your functions. No function pointers and no runtime setter (`platform.h:139-144`) |
| `MBEDTLS_PLATFORM_MEMORY` alone | real functions in `library/platform.c:47-55`, which call through two function pointers |

In the third case the pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`. Those default to `calloc` / `free`. If `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set, they become stubs instead: calloc returns NULL and free does nothing (`platform.c:25-42`).

## How a project substitutes its own allocator

**Compile time (no runtime cost):**
- Enable `MBEDTLS_PLATFORM_MEMORY`.
- Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. Both or neither must be set; `check_config.h:558-573` enforces this.
- Make the declarations visible in every translation unit. Put the definitions in the config header, or in a file named by `MBEDTLS_USER_CONFIG_FILE`, which `build_info.h:129` includes. The macros also need to be defined before `platform.h` is read.

**Runtime:**
- Enable `MBEDTLS_PLATFORM_MEMORY` but leave out the two macros.
- Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any library call that allocates. It always returns 0 and does no validation (`platform.c:57-63`).
- The pointers are plain globals with no synchronisation. Set them once at startup, and never swap them while objects allocated by the old pair are still alive. `free` must match the allocator that produced the pointer.

## What the library itself does with the facility

- **Single choke point.** Every module allocates through the wrappers. Examples are `ssl_cache.c:186`, `pem.c:422`, `ecp.c:1378` and `x509.c:531`. The only raw `free` in `library/` is inside a debug-only trace in `memory_buffer_alloc.c:404`.
- **Checks for NULL.** Failure is handled at each call site. A past fix (ChangeLog:173) was about a missing NULL check after `mbedtls_calloc()`.
- **Zeroise-then-free.** `mbedtls_zeroize_and_free()` (`platform_util.c:139-146`) wipes the buffer before freeing it. That matters for key material.
- **Built-in allocator.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-576`) hands the library a caller-supplied buffer as its heap. It installs its own calloc and free through `mbedtls_platform_set_calloc_free`, using mutex-guarded variants when `MBEDTLS_THREADING_C` is on. This is a ready-made runtime substitution that needs no `malloc` at all.

Scope note: I read the sources and config headers directly. I did not build the library or run a test, so the behaviour above is from code reading.