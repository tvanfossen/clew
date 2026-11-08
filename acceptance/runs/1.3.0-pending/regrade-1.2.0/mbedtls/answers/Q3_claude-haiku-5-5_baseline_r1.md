**Short answer:** library code never calls `calloc`/`free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`. What those names resolve to depends on the config, and at runtime they are either the libc functions or a pair of function pointers the application can replace.

## What gets called

There are three configurations, chosen in `mbedtls_config.h` and resolved in `include/mbedtls/platform.h:138-168`:

| Config | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` not defined | Macros for libc `calloc` / `free` (`platform.h:166-167`) |
| `MBEDTLS_PLATFORM_MEMORY` + `MBEDTLS_PLATFORM_CALLOC_MACRO` + `MBEDTLS_PLATFORM_FREE_MACRO` | Macros for your functions, chosen at compile time. No runtime setter exists. |
| `MBEDTLS_PLATFORM_MEMORY` alone | Real functions in `library/platform.c:47-55` that call through two function pointers |

In the third case, `platform.c:44-45` initialises the pointers to `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`. Those default to libc unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set. If no standard function is available, they become stubs: calloc returns NULL and free does nothing.

The call chain for the function-pointer case is:

```
library code → mbedtls_calloc() [platform.c:47] → mbedtls_calloc_func → calloc (or stub)
library code → mbedtls_free()   [platform.c:52] → mbedtls_free_func   → free   (or stub)
```

## How a project substitutes its allocator

1. **Runtime (most flexible).** Define `MBEDTLS_PLATFORM_MEMORY` and leave the two macros undefined. Then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57-63`) before any library allocation. The setter is declared only in this configuration.
2. **Compile time.** Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` together. The macros must be set as a pair. When both are present, `platform.c` drops the runtime setter entirely, so calling it fails to link.
3. **No standard library.** Define `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`, and optionally `MBEDTLS_PLATFORM_STD_MEM_HDR` to supply a header. Then either define `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` or rely on the stubs above.

The config doc says the `STD_CALLOC` and `CALLOC_MACRO` options cannot both be defined. The contract for your functions is the libc one: calloc must zero memory, free must accept NULL, and a free must receive only pointers the matching calloc returned.

## What the library does with the facility

- **Allocation volume.** `mbedtls_calloc(` appears about 169 times across 48 files in `library/`. The heaviest users are `ssl_tls.c` (26), `psa_crypto.c` (16), `cipher_wrap.c` (11) and `pk_wrap.c` (8). Allocation is per-object (contexts, buffers, key material).
- **No direct libc use.** A grep of `library/` for `malloc`/`calloc`/`realloc`/`free` finds only comments and one exception: `memory_buffer_alloc.c:404` calls libc `free(hdr->trace)` in the backtrace debug path. That pointer comes from `backtrace_symbols`, so libc free is the correct pair there.
- **Built-in alternative: `MBEDTLS_MEMORY_BUFFER_ALLOC_C`.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-576`) makes a fixed-size heap from a caller buffer. It installs its own `buffer_alloc_calloc` / `buffer_alloc_free` through the same `mbedtls_platform_set_calloc_free()` setter. With `MBEDTLS_THREADING_C` it uses mutex-wrapped variants. It never calls libc calloc or free.
- **Consequence.** Because the buffer allocator uses the same setter, it overrides any allocator the project registered earlier. It also requires `MBEDTLS_PLATFORM_MEMORY`, per the config doc.

## Caveats

- I did not check whether every heap free is preceded by zeroing. The zeroize calls I saw wipe context structs and stack buffers, not heap blocks passed to `mbedtls_free`.
- The advice to register the allocator before any allocation is my inference from the setter design. The header does not state it outright.