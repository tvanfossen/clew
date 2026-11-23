The library never calls `malloc`/`calloc`/`free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, and which real function runs is decided at build time or at runtime.

## What gets called

```
library code (ssl_tls.c, bignum.c, cipher_wrap.c, ...)
        │  mbedtls_calloc(n, sz) / mbedtls_free(p)
        ▼
include/mbedtls/platform.h:138-168 — chosen by config
  ├─ MBEDTLS_PLATFORM_MEMORY off           → macro → calloc / free        (no indirection)
  ├─ MEMORY + CALLOC_MACRO + FREE_MACRO    → macro → your functions       (compile-time, no indirection)
  └─ MEMORY only                           → real functions, platform.c:47-55
                                              │ call through function pointers
                                              ▼
                              mbedtls_calloc_func / mbedtls_free_func  (platform.c:44-45)
                                  default = MBEDTLS_PLATFORM_STD_CALLOC/FREE
                                  if undefined → stubs: calloc returns NULL, free is a no-op
```

- **Config off:** `platform.h:166-167` define `mbedtls_calloc` as `calloc` and `mbedtls_free` as `free`.
- **Compile-time substitution:** `platform.h:139-145` maps the names to `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. `check_config.h:548-575` requires that both macros be defined together.
- **Runtime substitution:** `platform.c:16-19` says the compile-time macros take precedence, and when both are defined the runtime setter is compiled out entirely.
- **Stubs:** the default `platform_calloc_uninit` and `platform_free_uninit` (`platform.c:24-42`) are used when nothing else is configured. Under `MBEDTLS_PLATFORM_MEMORY`, an unconfigured build fails every allocation with NULL.

## How a project substitutes its allocator

**Option A: compile time (zero overhead).** In the user config, enable `MBEDTLS_PLATFORM_C`, `MBEDTLS_PLATFORM_MEMORY`, and define both `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. Define both or neither. The `check_config.h` errors enforce this.

**Option B: runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` and leave the macros undefined, or define `MBEDTLS_PLATFORM_STD_CALLOC`/`_FREE` as the defaults. Then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other mbedtls call (`platform.c:57-63`). The setter does no NULL checks and always returns 0. It is a plain pointer write, not synchronized, so call it before threads start. Any substitute must tolerate `free(NULL)`, because the wrapper forwards whatever it receives.

## What the library does with the facility

- **Every allocation funnels through the wrappers.** Callers include `ssl_tls.c`, `bignum.c`, `cipher_wrap.c`, `pkparse.c`, `x509_crt.c` and the PSA core. `mbedtls_zeroize_and_free` in `common.h` also uses `mbedtls_free`. A grep of `library/` for raw `calloc|malloc|free|realloc` finds no direct calls except `memory_buffer_alloc.c:404`, `free(hdr->trace)`, which is inside `MBEDTLS_MEMORY_BACKTRACE`. I did not check how `trace` is allocated.
- **The library ships its own substitute.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) zeroes a static `heap` context, then installs its own allocator through `mbedtls_platform_set_calloc_free`. It uses the mutex-wrapped variants when `MBEDTLS_THREADING_C` is enabled (`:541-563`) and uses libc nowhere. It is the only library code that calls the setter.
- **Weak points in the bundled allocator:**
  - In the mutexed calloc, if unlock fails after a successful allocation, the function returns NULL and leaks the buffer (`:547-550`).
  - In the mutexed free, if the lock fails, the free is silently skipped and the block leaks (`:558-560`). The comment says this is deliberate: losing memory is preferred to corrupting the heap.
- **Design intent is tested.** The `component_test_psa_crypto_without_heap` component in `tests/scripts/components-configuration-crypto.sh` builds a configuration where the core library cannot use calloc/free while test code still can.