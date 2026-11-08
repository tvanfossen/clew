**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc`/`mbedtls_free`, and what those resolve to depends on the build configuration.

## What gets called

There are three configurations, chosen at compile time in `include/mbedtls/platform.h:127-168`:

| Config | `mbedtls_calloc` resolves to | Mechanism |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | `calloc` | Macro in `platform.h:166-167`. No wrapper function exists. |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_{CALLOC,FREE}_MACRO` | Your function, e.g. `my_calloc` | Macro in `platform.h:143-144`. Resolved at each call site. |
| `MBEDTLS_PLATFORM_MEMORY` alone | `mbedtls_calloc()` in `library/platform.c:47` | Calls through a function pointer that is set at runtime. |

In the third case the pointer is initialised to `MBEDTLS_PLATFORM_STD_CALLOC`, which defaults to `calloc` when `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is not set. If that define is set, the default is `platform_calloc_uninit` (`platform.c:25-33`), which always returns NULL. The same applies to free (`platform.c:36-45`).

Library call sites use the macro, for example `library/ssl_msg.c:2425` and `:2431`.

## How a project substitutes its allocator

**Compile time.** Both macros must be defined together. `check_config.h:558-573` rejects one without the other.

```c
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free
```

Your functions must have the signatures `void *(size_t, size_t)` and `void (void *)`. This route needs no runtime registration and does not link the platform wrapper.

**Runtime.** Enable only `MBEDTLS_PLATFORM_MEMORY` (which requires `MBEDTLS_PLATFORM_C`), then call the setter before any allocation:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

Set `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` if you want no libc `calloc`/`free` linked in. The config doc in `mbedtls_config.h:155-200` says you must then supply an allocator, or the uninitialised default will fail every allocation.

The repo's own tests toggle these through `scripts/config.py` (`tests/scripts/components-configuration-crypto.sh:160-171`, `components-configuration-platform.sh:45-47`).

## What the library does with the facility

- **Storage.** `platform.c:44-45` holds two static function pointers. `platform.c:57-63` writes them with no lock and no return-value check; the function always returns 0.
- **Compile-time macros win.** `platform.c:16-19` drops the runtime setter entirely when both macros are defined.
- **The library's own allocator uses the same hook.** `mbedtls_memory_buffer_alloc_init()` (`library/memory_buffer_alloc.c:566-576`) calls `mbedtls_platform_set_calloc_free()` itself. It installs the mutex-wrapped variant when `MBEDTLS_THREADING_C` is on, and the plain one otherwise. Calling it therefore swaps the global allocator as a side effect.
- **Teardown is incomplete.** `mbedtls_memory_buffer_alloc_free()` (`memory_buffer_alloc.c:602-608`) destroys the mutex and zeroises the heap context. It does not restore the previous function pointers. After it runs, `mbedtls_calloc` still points at the buffer allocator, which now has a zeroed heap. I read this from the code and did not run it.
- **One libc call remains.** `memory_buffer_alloc.c:404` calls `free(hdr->trace)` under `MBEDTLS_MEMORY_BACKTRACE`. I did not check where `trace` is allocated, so I can't say whether it is paired with libc or with the substituted allocator.

The index confirmed the symbol names and call sites, but its dossier reply for the allocator functions was too large to read in full, so the file-level findings above come from reading the source directly.