## Short answer

Mbed TLS never calls `calloc`/`free` directly in its own code. Every allocation goes through `mbedtls_calloc()`, and every release goes through `mbedtls_free()`. What those names resolve to depends on the build configuration:

| Configuration | `mbedtls_calloc` / `mbedtls_free` become |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | Macros for libc `calloc` / `free` (`include/mbedtls/platform.h:166-167`) |
| `MBEDTLS_PLATFORM_MEMORY` on, no macros | Real functions in `library/platform.c:47-54` that forward through two function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`. They start as `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE`, which default to libc `calloc` / `free` (`platform.h:83-88`). |
| `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Macros pointing at your functions. The `platform.c` wrappers are compiled out (`platform.c:20-22`). |

The default case is the one most people hit: `mbedtls_calloc` is a macro for `calloc`.

## How a project substitutes its allocator

**Option A: compile time (no runtime indirection).** Define in `mbedtls_config.h` or on the compiler command line:

```
MBEDTLS_PLATFORM_MEMORY
MBEDTLS_PLATFORM_CALLOC_MACRO = my_calloc
MBEDTLS_PLATFORM_FREE_MACRO   = my_free
```

`check_config.h:558-573` requires the two macros to be defined together. Your `my_calloc` and `my_free` must be declared where `platform.h` can see them, typically through `MBEDTLS_PLATFORM_STD_MEM_HDR` or a config-included header.

**Option B: runtime.** Define only `MBEDTLS_PLATFORM_MEMORY`, then call this before any Mbed TLS allocation:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);   /* always returns 0 */
```

The setter (`platform.c:57-62`) just assigns the two globals. It does no validation and is not synchronized.

**Option C: change the default target.** Define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` (`mbedtls_config.h:4113-4124`) to point at a different default. With `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`, the default is an uninitialized stub that always returns NULL.

## What the library requires of your allocator

- **`calloc` must zero the memory.** The config docs say so explicitly.
- **It may return NULL, and callers check for it.** Examples: `cmac.c:186`, `bignum_mod_raw.c:237`, `pem.c:422`, `ssl_cache.c:186`.
- **`free` is called unconditionally, including on NULL.** `mbedtls_zeroize_and_free()` (`platform_util.c:139-146`) only guards the zeroize step with a NULL check, then calls `mbedtls_free(buf)` regardless. Your free must accept NULL.
- **Secrets are zeroed before they are freed.** `mbedtls_zeroize_and_free` calls `mbedtls_platform_zeroize` first, so your `free` receives already-cleared memory. Key material and similar secrets are released this way.

## What the library does with the facility

- **Built-in allocator.** `MBEDTLS_MEMORY_BUFFER_ALLOC_C` (`library/memory_buffer_alloc.c`) is itself a client of this mechanism. `mbedtls_memory_buffer_alloc_init(buf, len)` carves a static caller-supplied buffer into a free-list heap and calls `mbedtls_platform_set_calloc_free` on its own functions (`memory_buffer_alloc.c:572-575`). The threaded variant wraps them in a mutex. Consequences:
  - Calling it silently overrides any allocator you set earlier.
  - The heap is a single process-wide static, so it is one heap per process.
- **Direct libc calls.** In `library/*.c`, the only raw `free()` I found is at `memory_buffer_alloc.c:404`, in the `MBEDTLS_MEMORY_BACKTRACE` path. I did not trace how that trace buffer is allocated. Other `calloc`/`free` mentions are comments.

## Caveats

- The runtime setter is a plain global write. Call it before any threads start, or before the first Mbed TLS call.
- Mixing allocators is unsafe: memory from `calloc` must not be passed to your `free`, and the reverse is also true. Objects allocated before a runtime switch will be freed by the new function.
- A NULL pointer passed to the setter is not checked. The first allocation would call through NULL.

I didn't build or run anything. This comes from reading the source, and I searched only `library/*.c` and the headers for direct libc calls.

One tool note: a PostToolUse hook suggested calling a `dossier` tool. It isn't in this session's tool set, so I ignored it and worked from the source directly.