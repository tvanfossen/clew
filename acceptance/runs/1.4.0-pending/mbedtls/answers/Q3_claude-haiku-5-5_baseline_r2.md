**Short answer:** Library code calls `mbedtls_calloc()` and `mbedtls_free()`. What those names resolve to depends on three config options. A project substitutes its allocator either at compile time (macros) or at runtime (a function-pointer setter). The library also uses the runtime hook itself for its optional static-buffer heap.

## What gets called

Roughly 100 call sites in `library/` use `mbedtls_calloc`/`mbedtls_free`. For example, `x509.c:531`, `ssl_cache.c:186`, `pem.c:422`, `ecp.c:1378` and `cipher.c:291`. The resolution, from `include/mbedtls/platform.h:138-168` and `library/platform.c`:

| Config | `mbedtls_calloc` resolves to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default; `mbedtls_config.h:208` is commented out) | `#define mbedtls_calloc calloc` (plain libc, `platform.h:166-167`) |
| `MBEDTLS_PLATFORM_MEMORY` + both `_CALLOC_MACRO` and `_FREE_MACRO` | A macro that expands to your function. No runtime indirection (`platform.h:139-144`) |
| `MBEDTLS_PLATFORM_MEMORY` only | Real functions in `platform.c:47-54` that dispatch through static pointers. Those start at `MBEDTLS_PLATFORM_STD_CALLOC`/`_FREE`, which default to `calloc`/`free` if libc is present, otherwise to stubs (`platform.c:24-42`). Stubs return NULL and do nothing. |

The macro pair must be defined together or not at all (`check_config.h:558-573`).

## How a project substitutes its allocator

**Compile time (no runtime cost):**
```
MBEDTLS_PLATFORM_MEMORY
MBEDTLS_PLATFORM_CALLOC_MACRO = my_calloc
MBEDTLS_PLATFORM_FREE_MACRO   = my_free
```

**Runtime:** define only `MBEDTLS_PLATFORM_MEMORY`, then call early, before any Mbed TLS allocation:
```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```
`my_calloc` must have the signature `void *(size_t, size_t)`, and `my_free` must be `void (void *)`.

**Default only:** `MBEDTLS_PLATFORM_STD_CALLOC`/`_FREE` redirect the default without a runtime call. Not defining them with `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` leaves the stubs in place.

Constraints I confirmed in the code:
- Everything allocated through `mbedtls_calloc` must be released through `mbedtls_free` (`asn1.h` documents this for list-freeing paths).
- `mbedtls_platform_set_calloc_free` stores the pointers without validating them and always returns 0 (`platform.c:57-63`). A NULL pointer fails later, at the first allocation.
- The setter has no synchronization. Call it before threads start.
- Callers must check for NULL. `ChangeLog:173` records a bug where an allocation failure went unchecked.

## What the library does with the facility

- **It does not call libc allocators directly.** My grep of `library/` found only one bare `free(hdr->trace)` in `memory_buffer_alloc.c:404`, which is under backtrace debugging. I did not trace where that pointer was allocated.
- **It ships its own allocator on top of the hook.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-576`) calls `mbedtls_platform_set_calloc_free` with its own `buffer_alloc_calloc`/`buffer_alloc_free`. It serves allocations from the caller's buffer and never touches the heap. With `MBEDTLS_THREADING_C` it installs mutex-wrapped variants (`:541-563`). It requires `MBEDTLS_MEMORY_BUFFER_ALLOC_C` plus `MBEDTLS_PLATFORM_MEMORY` (`check_config.h:426-428`).
- **Side effect:** that init overwrites the global pointers, so it replaces whatever allocator was installed before. Its free path logs a FATAL message and handles invalid pointers (`memory_buffer_alloc.c:373, 390`).