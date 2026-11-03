**Short answer:** library code never calls `calloc` or `free` directly. It calls `mbedtls_calloc(n, size)` and `mbedtls_free(p)`, and what those names resolve to depends on the build configuration.

```
library code: mbedtls_calloc(n, sz)
  │
  ├─ MBEDTLS_PLATFORM_MEMORY off (default)
  │     └─ macro → calloc                                  platform.h:167
  │
  ├─ MBEDTLS_PLATFORM_MEMORY on, no CALLOC_MACRO
  │     └─ mbedtls_calloc() in platform.c:47
  │          └─ (*mbedtls_calloc_func)(n, sz)              static ptr, platform.c:44
  │             initial value MBEDTLS_PLATFORM_STD_CALLOC (= calloc)
  │
  └─ MBEDTLS_PLATFORM_MEMORY + CALLOC_MACRO + FREE_MACRO
        └─ macro → your function, direct, no runtime hook  platform.h:144
```

`mbedtls_free` follows the same pattern through `mbedtls_free_func`. This is my reading of the gate metadata the index holds, not the preprocessor text, so confirm the exact `#if` arms in `platform.h` around lines 130–170 before relying on them.

**How a project substitutes its allocator**

1. **Compile-time macros.** Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the project's config. The index has no definition site for the two macros, so the project supplies them. Calls then expand straight to the project's functions with no runtime indirection.
2. **Compile-time, std-name override.** Keep `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_STD_CALLOC` / `_STD_FREE` to the project's functions. The repo's test config does this in `tests/configs/user-config-malloc-0-null.h`: `custom_calloc` (lines 12–18) returns NULL for zero sizes and otherwise wraps `calloc`.
3. **Runtime.** Call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`platform.c:57-63`). It sets both pointers and returns 0. The index places it under the `MBEDTLS_PLATFORM_MEMORY` gate, so it exists only in pointer mode. The calloc and free pointers are set together, so pass a matching pair.

**What the library itself does with the facility**

- **Everything routes through the two names.** The callers list for `mbedtls_calloc` covers cipher context alloc (`cipher_wrap.c`), `mbedtls_md_setup` (`md.c`, via the `ALLOC` macro), bignum grow/shrink, `resize_buffer` and `ssl_setup` in `ssl_tls.c`, x509 and PKCS#7 parsing, PSA slot and key allocation, and LMS. Frees go through `mbedtls_free`, including `mbedtls_zeroize_and_free` in `common.h`.
- **It uses the facility to install its own allocator.** `mbedtls_memory_buffer_alloc_init` (`memory_buffer_alloc.c:566-600`) takes a caller-supplied buffer, sets up an in-buffer heap that never calls `calloc`/`free`, and registers itself with `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it registers `buffer_alloc_calloc_mutexed` (lines 541-552), which takes the heap mutex around the allocation. The selftest `main` calls it.
- **Two things I noticed in that init.** If `len` is too small, it returns early after the pointers are already installed, with the heap left unset, and it has no error return. The index does not show what allocations then do.
- **A stub default.** `platform_calloc_uninit` (`platform.c:25-30`) always returns NULL, and the index shows it as the `MBEDTLS_PLATFORM_STD_CALLOC` expansion at `platform.c:32`. My inference from that gate: a build with no std allocator has every allocation failing until the project calls `set_calloc_free`. The index does not state this directly.