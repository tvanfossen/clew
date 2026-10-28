## What mbedtls calls

Library code never calls `calloc` or `free` directly. It calls `mbedtls_calloc(nmemb, size)` and `mbedtls_free(ptr)`, and what those names resolve to depends on the build configuration. The resolution is in `include/mbedtls/platform.h:136-160`:

| Configuration | `mbedtls_calloc` / `mbedtls_free` become |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` not defined (the shipped default; `mbedtls_config.h:208` is `//#define`) | the libc `calloc` / `free` directly, via macros (`platform.h:~170`) |
| `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | those macros, expanded at compile time, no indirection |
| `MBEDTLS_PLATFORM_MEMORY` alone | real functions in `library/platform.c:37-47`, which call through two function pointers |

In the third case the chain is:

```
library code → mbedtls_calloc() → (*mbedtls_calloc_func)() → default or your function
```

The pointers are initialised to `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` (`platform.c:~31-33`). Those default to libc `calloc`/`free` when you don't define them (`platform.h:~84-90`). If you define `MBEDTLS_PLATFORM_STD_CALLOC` yourself without a replacement, the library substitutes `platform_calloc_uninit`, which always returns NULL (`platform.c:24-30`). The config docs call this out explicitly (`mbedtls_config.h:4120`).

## How a project substitutes its allocator

Two routes, and the compile-time one wins when both are present.

**1. Compile-time macros.** In your `mbedtls_config.h` or a user config header (`MBEDTLS_USER_CONFIG_FILE`):

```c
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free
```

Both macros must be defined together; the config docs say so (`mbedtls_config.h:198`). Your `my_calloc` must match the `calloc` signature. Nothing in the library's runtime path changes, and the runtime setter is compiled out (`platform.c:15-22`).

**2. Runtime setter.** Define only `MBEDTLS_PLATFORM_MEMORY`, then at startup call:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

The function is declared at `platform.h:160`. It replaces the two pointers (`platform.c:57-63`). It is global, not per-context, and it returns 0 without validating its arguments.

Optionally, `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE` can point the default at your functions without touching the pointers at runtime.

## What the library does with the facility

Mbed TLS does not decide anything itself; it only calls through what you installed. Every allocation in the library goes through `mbedtls_calloc`, and every release through `mbedtls_free`. For example, `library/md.c` uses an `ALLOC` macro that calls `mbedtls_calloc(1, sizeof(...))` and returns `MBEDTLS_ERR_MD_ALLOC_FAILED` on NULL. `mbedtls_oid_from_numeric_string` documents that its output must be freed with `mbedtls_free()`, which is the contract a custom allocator must honour.

The library also ships its own consumer of the facility: the stack allocator in `library/memory_buffer_alloc.c`. `mbedtls_memory_buffer_alloc_init(buf, len)` (line ~568) sets the global pointers to its own `buffer_alloc_calloc` / `buffer_alloc_free`, or to `_mutexed` variants when `MBEDTLS_THREADING_C` is on. Allocations then come from the caller's fixed buffer and never reach libc. Because the setter is global, calling `mbedtls_memory_buffer_alloc_init` replaces whatever allocator you installed earlier, and the reverse is also true.

## Caveats

- I did not verify that every library `free` goes through `mbedtls_free`, nor that `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is gated on `MBEDTLS_PLATFORM_MEMORY`. Both are worth a grep before relying on them.
- The clew `dossier` for the allocator symbols overflowed the reply size, so I answered from direct reads of `platform.c`, `platform.h`, `mbedtls_config.h` and `memory_buffer_alloc.c`. The index confirmed the names and locations.