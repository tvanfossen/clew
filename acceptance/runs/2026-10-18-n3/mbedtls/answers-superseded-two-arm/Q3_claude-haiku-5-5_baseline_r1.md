**Short answer:** every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those are either thin wrappers around libc (default) or wrappers that dispatch through function pointers you install at runtime or compile time. The library's own `memory_buffer_alloc` is one such allocator, and it installs itself through that same hook.

**What gets called**

The resolution depends on `MBEDTLS_PLATFORM_MEMORY` (`include/mbedtls/mbedtls_config.h:155-208`, off by default):

| Config | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off | Macros `#define mbedtls_calloc calloc`, `mbedtls_free free` (`include/mbedtls/platform.h:163-168`). Direct libc calls, no indirection. |
| On, plus `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Macros pointing at your functions, resolved at compile time (`platform.h:139-144`). |
| On, without those macros | Real functions `mbedtls_calloc()` / `mbedtls_free()` in `library/platform.c:47-55`. These call through static function pointers `mbedtls_calloc_func` / `mbedtls_free_func` (`platform.c:44-45`). |

The pointers start as `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`, which default to libc `calloc`/`free` (`platform.h:83-88`). If the user sets `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`, they start as stub functions that fail (calloc returns NULL) or do nothing (free). `platform.c:24-42` supplies those stubs.

**How a project substitutes its allocator**

Option A, compile time (no runtime cost):
1. Enable `MBEDTLS_PLATFORM_MEMORY` and `MBEDTLS_PLATFORM_C`.
2. Define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`, pointing at your functions. They must be set together (`check_config.h:558-573`).
3. Your calloc must zero memory and return NULL on failure. Your free must accept NULL.

Option B, runtime:
1. Enable `MBEDTLS_PLATFORM_MEMORY` and `MBEDTLS_PLATFORM_C`, leaving the macros undefined.
2. Optionally define `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` as defaults.
3. Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other library call. It is a single global, not per context (`platform.c:57-63`).

`MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_STD_CALLOC` cannot both be defined (`check_config.h:567-569`).

**What the library itself does with the facility**

- **Bundled allocator.** `MBEDTLS_MEMORY_BUFFER_ALLOC_C` provides a heap over a caller-supplied buffer. `mbedtls_memory_buffer_alloc_init()` calls `mbedtls_platform_set_calloc_free()` with its own `buffer_alloc_calloc` / `buffer_alloc_free` (`library/memory_buffer_alloc.c:566-576`). Calling it therefore redirects every library allocation into that buffer. With `MBEDTLS_THREADING_C`, it uses mutex-wrapped variants (`memory_buffer_alloc.c:540-563`).
- **No raw libc allocation in the library.** A grep of `library/` for `malloc`/`calloc`/`free(` found only comments, plus `free(hdr->trace)` inside the debug path of `memory_buffer_alloc.c:404`. Everything else uses `mbedtls_calloc` / `mbedtls_free`, which is why one hook covers the whole library. For example, `psa_crypto.c` alone has 24 references.
- **Fallback stubs.** With `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`, an unset calloc returns NULL, so the library fails cleanly rather than crashing.

**Caveats**

- The hook is process-global. Installing a new allocator mid-session affects blocks already allocated, so a block must be freed with the same allocator that produced it.
- The runtime setter is not synchronized. Set it once at startup, before threads start.
- Both `mbedtls_calloc` and `mbedtls_free` must be installed together. Setting only one leaves the other's old function in place.

I did not run a build or test to confirm the runtime behaviour. The conclusions come from reading `platform.h`, `platform.c`, `memory_buffer_alloc.c`, `mbedtls_config.h` and `check_config.h`.