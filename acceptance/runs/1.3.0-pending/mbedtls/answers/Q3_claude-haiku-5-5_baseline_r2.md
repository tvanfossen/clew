**Short answer:** by default, `mbedtls_calloc` and `mbedtls_free` are the C library's `calloc` and `free`, with no indirection. Substitution happens at compile time with two macros, or at runtime through `mbedtls_platform_set_calloc_free()`. The library's only own use of the facility is the optional buffer allocator, which installs itself through that same setter.

**What gets called**

The library never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, about 170 call sites across 48 files (`ssl_tls.c`, `psa_crypto.c`, `x509*.c`, `bignum*.c`, and others). What those names resolve to depends on the config (`include/mbedtls/platform.h:138-168`):

| Config | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off | `calloc` / `free` via macro. No indirection. |
| On, both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `_FREE_MACRO` set | Those macros, at compile time. `platform.c` drops its runtime code entirely. |
| On, macros not set | Real functions in `library/platform.c:47-55`. They call through static function pointers, initialised to `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE` (default `calloc`/`free` unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`). |

```
library code ──> mbedtls_calloc() ──> mbedtls_calloc_func ──> (default calloc | your fn | buffer allocator)
```

If `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set and no `STD_CALLOC` is provided, the pointer is `platform_calloc_uninit`, which returns NULL. Likewise the uninitialised free does nothing (`platform.c:25-42`).

**How a project substitutes its allocator**

1. **Compile time (no runtime cost):** define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc`, and `MBEDTLS_PLATFORM_FREE_MACRO=my_free` in the user config. Both macros must be set together. Setting `STD_CALLOC` at the same time is an error (per the doc at `mbedtls_config.h:197`). The config header's own comment (`mbedtls_config.h:154-203`) is the reference.
2. **Runtime:** define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any library allocation. This is the only way to do it in the function-pointer path. Two things to know from the code:
   - The setter does no NULL checks and no locking (`platform.c:57-63`). Passing NULL means a crash on the first allocation, and the swap is not thread-safe.
   - The allocator contract is in `mbedtls_config.h:4113-4133`. `calloc` must zero memory and return NULL for a zero-size request if it chooses. `free(NULL)` must be a no-op.

**What the library does with the facility itself**

- **Default path:** nothing. The library ships only the pointer indirection and the default `calloc`/`free`.
- **Buffer allocator (`MBEDTLS_MEMORY_BUFFER_ALLOC_C`):** `library/memory_buffer_alloc.c` provides a heap carved from a caller-supplied static buffer. `mbedtls_memory_buffer_alloc_init()` (line 566) zeroes the heap and then calls `mbedtls_platform_set_calloc_free()` itself, pointing it at `buffer_alloc_calloc` or, with `MBEDTLS_THREADING_C`, a mutex-wrapped variant. So the library uses its own setter on the project's behalf. Its self-tests (lines 658-740) call `mbedtls_calloc`/`mbedtls_free` to exercise the heap.
- **Global state caveat:** the heap is a single static `heap` struct, so there is one heap per process. `mbedtls_memory_buffer_alloc_free()` (line 602) zeroes the heap but does not reset the function pointers. Later calls therefore still route to the buffer allocator, which returns NULL because `heap.buf` is now NULL (`memory_buffer_alloc.c:210`). I read this from the code and did not run it.
- **Ordering:** calling `mbedtls_memory_buffer_alloc_init()` after your own `mbedtls_platform_set_calloc_free()` silently replaces your allocator. Set yours after the buffer allocator's init, or don't mix the two.
- **Other raw libc calls:** the only direct `free()` in `library/` is `memory_buffer_alloc.c:404`, which frees the `backtrace_symbols()` array. That array comes from libc `malloc`, so the pairing is correct, and it sits inside the allocator itself.

I didn't build or run any of this. The claims above come from reading `platform.h`, `platform.c`, `mbedtls_config.h` and `memory_buffer_alloc.c`.