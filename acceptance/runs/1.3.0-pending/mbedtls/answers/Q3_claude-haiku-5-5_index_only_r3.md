**Short answer:** mbedtls never calls `malloc`/`calloc` directly in its library code. Every allocation goes through `mbedtls_calloc()` / `mbedtls_free()`, which dispatch through two function pointers that a project can replace at runtime. The default pointers point at libc.

**What gets called**

```
library code (ecp.c, ssl_tls.c, x509_crt.c, psa_crypto.c, ...)
  └─ mbedtls_calloc(n, size) ─┐
  └─ mbedtls_free(p) ─────────┤  (platform.h: macro or function, depending on config)
                              ▼
   platform.c:47  mbedtls_calloc()  → (*mbedtls_calloc_func)(n, size)
   platform.c:52  mbedtls_free()    → (*mbedtls_free_func)(p)
                              ▼
   platform.c:44-45  static pointers, initialised to
     MBEDTLS_PLATFORM_STD_CALLOC / MBEDTLS_PLATFORM_STD_FREE
     (platform.h:84 → libc calloc/free by default)
```

- `mbedtls_calloc` and `mbedtls_free` are called from many modules, including `cipher_wrap.c` context allocators, `ecp.c`, `pk_wrap.c`, `ssl_tls.c`, `x509_crt.c`, `pkcs7.c`, `lms.c` and `psa_crypto*.c`. `mbedtls_zeroize_and_free` in `common.h` also goes through `mbedtls_free`.
- `mbedtls_platform_set_calloc_free(calloc_func, free_func)` (`platform.c:57-63`) overwrites the two pointers and always returns 0. It does no NULL check and no validation.

**How a project substitutes its allocator**

Two routes, both in the index:

1. **Runtime (no rebuild):** call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any mbedtls allocation. This is the path the library's own helpers use.
2. **Compile-time:** define `MBEDTLS_PLATFORM_MEMORY` together with `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`, which route `mbedtls_calloc`/`mbedtls_free` at the preprocessor level (`platform.h:143-144`). The index has no shipped definition site for those two macros, so the project must supply them in its own config. The repo's `tests/configs/user-config-malloc-0-null.h` shows the pattern: it sets `MBEDTLS_PLATFORM_MEMORY` and maps `MBEDTLS_PLATFORM_STD_CALLOC` to `custom_calloc`.

**What the library does with the facility**

- **Default:** libc `calloc`/`free`.
- **No standard functions:** if the project removes the standard functions and does not define the macro, `platform.c:25-32` falls back to `platform_calloc_uninit`, which always returns NULL. Every allocation then fails until the project calls `mbedtls_platform_set_calloc_free`. This is inferred from the gating, not from a test.
- **Built-in heap:** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) carves allocations out of a caller-supplied buffer and never calls libc. It installs its own allocator by calling `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it installs a mutex-wrapped variant (`buffer_alloc_calloc_mutexed`, `:541-552`). The installation is process-global, so it replaces whatever allocator was set before.

**Limits of this answer**

- The index does not give me the exact `#if` expression for `platform.h:138-168` or `platform.c:20-64`. I know which macros gate them and what each expands to, but not the precise branch logic. Read those lines to confirm which path a given config takes.
- I did not verify that no library file calls libc `calloc` directly. The index shows the library's `mbedtls_calloc` callers, not an exhaustive absence of raw calls.