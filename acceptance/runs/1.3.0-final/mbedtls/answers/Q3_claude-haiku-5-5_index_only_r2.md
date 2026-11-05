**Short answer:** every heap allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those two functions are thin wrappers that call through a pair of pointers, and by default the pointers lead to libc `calloc` and `free`. A project swaps the allocator either at compile time (macros) or at run time (`mbedtls_platform_set_calloc_free`). The library's own stack-based allocator uses the same hook in reverse.

**The call path**

```
library code (cipher_wrap.c, ecp.c, x509*.c, ssl_*.c, psa_*.c, pem.c ...)
    │  mbedtls_calloc(n, sz)   /   mbedtls_free(p)
    ▼
library/platform.c:47-55   (wrappers; compiled under MBEDTLS_PLATFORM_MEMORY)
    │  (*mbedtls_calloc_func)(n, sz)   /   (*mbedtls_free_func)(p)
    ▼
static pointers, platform.c:44-45, initialised to MBEDTLS_PLATFORM_STD_CALLOC / _FREE
    │
    ▼  default: libc calloc / free  (platform.h:84, :87)
```

- **Default build:** `MBEDTLS_PLATFORM_MEMORY` is off (`mbedtls_config.h:208`). The standard functions are `calloc` and `free` (`platform.h:84`, `:87`). `mbedtls_calloc` and `mbedtls_free` are macros that map to the libc calls, so there is no extra indirection.
- **Callers:** `mbedtls_calloc` has many callers across the library, including the cipher context allocators in `cipher_wrap.c`, `ecp_mul_comb` and `ecp_normalize_jac_many` in `ecp.c`, `mbedtls_pem_read_buffer` in `pem.c`, the X.509 parsers, the SSL session and cache code, and the PSA slot allocators. `mbedtls_free` has similarly broad use, including `mbedtls_zeroize_and_free` in `common.h`.

**How a project substitutes its allocator**

Two routes, both documented in the `MBEDTLS_PLATFORM_MEMORY` member docs (`configs/ext/tfm_mbedcrypto_config_profile_medium.h`):

1. **Run time.** Enable `MBEDTLS_PLATFORM_MEMORY` and leave the `_MACRO` options undefined. The library then exposes `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`library/platform.c:57-63`). Call it once, before any library allocation. The function only stores the two pointers, always returns 0, and does no validation or locking. Treat it as a process-wide setting. The docs say `mbedtls_free` must accept `NULL`.
2. **Compile time.** Enable `MBEDTLS_PLATFORM_MEMORY` and define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. `mbedtls_calloc` and `mbedtls_free` then expand directly to your functions. The repo's own examples are `tests/configs/user-config-malloc-0-null.h`, which uses `custom_calloc`, and `component_test_platform_calloc_macro`, which sets `CALLOC_MACRO calloc`. The index does not show the exact branch that excludes the runtime pointers in this mode, so I'd verify that in `platform.c` before relying on it.

**What the library does with the facility itself**

- **Stack-based allocator.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) carves allocations out of a caller-supplied buffer and never calls libc. It installs its own functions by calling `mbedtls_platform_set_calloc_free`. It uses the mutexed variants when `MBEDTLS_THREADING_C` is on. This is the built-in example of substitution. It needs `MBEDTLS_PLATFORM_C` and `MBEDTLS_PLATFORM_MEMORY`, and it replaces the `calloc`/`free` calls rather than adding to them.
- **Test and benchmark code.** The benchmark program and the selftests use the same hook. `component_test_psa_crypto_without_heap` builds a configuration where the core library cannot call `calloc`/`free` while test code and the driver can.

**Things to check**

- The index shows the `MBEDTLS_PLATFORM_STD_CALLOC` documentation naming `mbedtls_platform_std_calloc`, but no such symbol exists in this build. The docs and the code disagree on that name.
- Because the pointers are process-global, a project cannot use one allocator for one connection and another for a second. The docs don't offer per-context allocators.