**Short answer:** every library allocation goes through `mbedtls_calloc()` / `mbedtls_free()`. Those forward to two static function pointers in `library/platform.c`, which default to the C standard library. A project swaps the allocator either at build time or at runtime. The library's own memory allocator, `memory_buffer_alloc`, uses the same hook to take over allocation entirely.

**Call chain**

```
library code  ──►  mbedtls_calloc(n, size)     library/platform.c:47
                     │  (*mbedtls_calloc_func)(n, size)
                     ▼
               mbedtls_calloc_func  (static, platform.c:44)
                 = MBEDTLS_PLATFORM_STD_CALLOC by default (calloc)

library code  ──►  mbedtls_free(p)             library/platform.c:52
                     │  (*mbedtls_free_func)(p)
                     ▼
               mbedtls_free_func  (static, platform.c:45)
                 = MBEDTLS_PLATFORM_STD_FREE by default (free)
```

The library never calls `calloc`/`free` directly in the code I could see. The `calloc(` search returned 40 hits and only one was outside the library (`programs/wince_main.c`). That search was capped at 40, so it is not exhaustive. Most allocation sites are `mbedtls_calloc(1, sizeof(...))` in `cipher_wrap.c`, `pk_wrap.c`, `psa_crypto.c`, `ssl_tls.c`, `bignum.c` and `bignum_mod_raw.c`. The index reports 147 callers of `mbedtls_calloc` and 133 of `mbedtls_free`.

**How a project substitutes its allocator**

1. **Compile time (the usual route).** Define `MBEDTLS_PLATFORM_MEMORY` in the config. The config file `tests/configs/user-config-malloc-0-null.h` does this and sets `MBEDTLS_PLATFORM_STD_CALLOC` to `custom_calloc` (line 21). Per the index, the `MBEDTLS_PLATFORM_MEMORY` default is off in `mbedtls_config.h:208`, and the calloc/free macro switches are gated on it. I inferred the exact `#if` structure from the gate records; I did not read the header bodies.
2. **Runtime.** Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57`). It just assigns the two pointers and returns 0. It takes no lock, so it should run before any other thread starts using the library. That is an inference from the code, not something the index states.

**What the library does with the facility**

- **Stack/heap allocator.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566`) carves allocations out of a caller-supplied buffer and never calls `calloc`/`free`. It installs its own functions via `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it installs mutex-wrapped variants (`buffer_alloc_calloc_mutexed`, line 541), which lock around `buffer_alloc_calloc`.
- **No-heap builds.** When `MBEDTLS_PLATFORM_STD_CALLOC` is not defined, the default calloc is `platform_calloc_uninit` (`platform.c:25`), which always returns NULL. A library built this way cannot allocate unless a project installs its own functions. The index has a component, `component_test_psa_crypto_without_heap`, that builds this way: test code may use calloc/free, but the core library may not.

**Not verified:** the `#if` bodies in `platform.h` and `platform.c`, and whether the library ever allocates outside `mbedtls_calloc`. The index answers from call edges and doesn't show raw `malloc` calls. Reading `include/mbedtls/platform.h` lines 84–170 would settle the exact macro wiring.