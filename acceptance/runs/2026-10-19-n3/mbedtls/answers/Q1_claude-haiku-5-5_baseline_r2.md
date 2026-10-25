**Short answer:** in the default configuration, nothing inside mbedtls runs concurrently and nothing is locked. The mutex code is compiled out entirely. Any concurrency comes from the application, and the library gives no protection to shared objects.

**Why the mutexes are absent**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, so it is off by default.
- `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also commented out.
- `library/threading.c` is wrapped in `#if defined(MBEDTLS_THREADING_C)` (line 18), so the backend, the function pointers, and the global mutex definitions are all excluded.
- Every per-object lock is guarded by the same macro. The guard is in `ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, `memory_buffer_alloc.c`, and the PSA paths in `psa_crypto.c`.
- The library creates no threads.

**What runs concurrently**

Only what the application makes happen. If an application calls mbedtls from several threads, nothing serializes those calls. The header docs say this is unsafe for PSA, and for TLS/X.509/PK when `MBEDTLS_USE_PSA_CRYPTO` is on. They also say TLS 1.3 needs the layer regardless of configuration (`mbedtls_config.h`, the `MBEDTLS_THREADING_C` block around line 3740).

**What is protected, and by what, when enabled**

| Object | Guard when `MBEDTLS_THREADING_C` is on |
|---|---|
| Per-context state: CTR_DRBG, HMAC_DRBG, entropy, SSL cache, cookie, ticket | Per-object `mbedtls_mutex_t` around the operation |
| `memory_buffer_alloc` heap | One global mutex (`heap.mutex`) |
| PSA key slots and state transitions | `mbedtls_threading_key_slot_mutex` |
| PSA global data (non-RNG) | `mbedtls_threading_psa_globaldata_mutex` |
| PSA RNG state | `mbedtls_threading_psa_rngdata_mutex` |
| `gmtime` fallback | `mbedtls_threading_gmtime_mutex`, only when no POSIX thread-safe `gmtime_r` is available |
| `readdir` (FS I/O) | `mbedtls_threading_readdir_mutex` |

**Things to note**

- `check_config.h` (lines 995–1010) makes `MBEDTLS_THREADING_C` require exactly one backend. Enabling it without ALT or PTHREAD fails the build.
- The only in-tree thread user is `programs/ssl/ssl_pthread_server.c`, which is a demo. It needs `MBEDTLS_THREADING_PTHREAD` and is not part of the library.
- For a multithreaded application you must enable `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`, and call `mbedtls_threading_set_alt()` before any other library call if you use ALT. Otherwise the default config leaves PSA global state and any shared context unprotected.

I did not build or run anything. These conclusions come from reading the config header, `threading.c`, and the guards at the call sites.