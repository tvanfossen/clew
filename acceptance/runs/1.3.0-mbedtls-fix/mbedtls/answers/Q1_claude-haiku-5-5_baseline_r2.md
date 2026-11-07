**Short answer:** in the default configuration, the library runs no concurrency of its own and protects nothing. The mutex layer is compiled out. Any concurrency is whatever threads your application puts into the library, and those threads share unprotected state.

**What is actually configured**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787`. `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also commented out (lines 2185, 2196).
- `library/threading.c` wraps its entire body in `#if defined(MBEDTLS_THREADING_C)`, so no mutex function pointers or global mutexes exist.
- Every `mbedtls_mutex_lock/unlock` call site in the library is guarded by `#if defined(MBEDTLS_THREADING_C)`, so none are compiled in.
- The library creates no threads.

**What runs concurrently**

Only your application's threads. Each thread may call into mbedtls at the same time, and nothing serializes them.

**Shared state that is unprotected by default**

| Area | Shared state | Protection in default build |
|---|---|---|
| PSA (`MBEDTLS_PSA_CRYPTO_C` is on) | `global_data` init flags, RNG state, key-slot table, `psa_crypto_init()` refcount | None |
| Entropy (`MBEDTLS_ENTROPY_C`) | entropy context and its sources | None |
| CTR_DRBG and HMAC_DRBG (both on) | DRBG state | None |
| SSL session cache, ticket, cookie | session/ticket/cookie tables | None |
| `gmtime` fallback | static buffer in libc `gmtime()` | Only if the platform lacks `gmtime_r` and the fallback path is used; the lock exists only under `MBEDTLS_THREADING_C` |

**Documented contract vs. default**

`mbedtls_config.h` (around lines 3740–3780) says `MBEDTLS_THREADING_C` must be enabled for any multithreaded use of PSA functions, for TLS 1.3 connections "regardless of the compile-time configuration", and for TLS/X.509/PK calls when `MBEDTLS_USE_PSA_CRYPTO` is on. Since `MBEDTLS_PSA_CRYPTO_C` is on and `MBEDTLS_THREADING_C` is off, the stock build is not safe for multithreaded PSA or TLS 1.3 use, even though the header calls that out explicitly.

**What the mutexes protect when enabled**

Enabling `MBEDTLS_THREADING_C` plus `MBEDTLS_THREADING_PTHREAD` adds:

- Global mutexes: `mbedtls_threading_key_slot_mutex`, `mbedtls_threading_psa_rngdata_mutex`, `mbedtls_threading_psa_globaldata_mutex`, and `mbedtls_threading_gmtime_mutex`. The readdir mutex is added under `MBEDTLS_FS_IO`.
- Per-object mutexes initialised in each `*_init()`: entropy, CTR_DRBG, HMAC_DRBG, the memory_buffer_alloc heap, SSL cache, SSL ticket, and SSL cookie.

Those are the call sites I confirmed. Other modules, including `rsa.c`, also contain guards that I did not trace.

**Caveats**

- I did not run a build or a thread-sanitizer test; this is from reading the source.
- The reading assumes a POSIX platform, where `gmtime_r` is used and the gmtime mutex is not needed.

**If you want thread safety**

Enable `MBEDTLS_THREADING_C` and either `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`. Without it, the safe pattern is one context per thread, with no sharing across threads.