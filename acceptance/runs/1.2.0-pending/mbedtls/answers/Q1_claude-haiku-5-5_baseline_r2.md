**Short answer:** in the default configuration the library has no locking at all. It never creates threads, so it runs concurrently only when your application calls it from several threads. Nothing protects the shared state the library keeps, so the application has to serialize access itself.

**Why the default is unprotected**

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`). `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also off.
- Because of that, `library/threading.c` compiles to nothing, the mutex type and lock/unlock function pointers are not declared, and every `#if defined(MBEDTLS_THREADING_C)` lock in the library is compiled out.

**What is enabled by default and holds shared state**

| Component | Default | Shared state with no lock |
|---|---|---|
| PSA (`MBEDTLS_PSA_CRYPTO_C`, line 3334) | on | `static psa_global_data_t global_data` (`library/psa_crypto.c:124`) holds the RNG state, the initialization flag and the key-slot state. Its locks are compiled out. |
| SSL session cache (`MBEDTLS_SSL_CACHE_C`, line 3670) | on | `ssl_cache.c:84` takes `cache->mutex` only under `THREADING_C`. Concurrent servers sharing one cache race on it. |
| CTR_DRBG / HMAC_DRBG / entropy contexts | on (via their modules) | `ctr_drbg.c:703` and `entropy.c:93` lock a per-context mutex only under `THREADING_C`. |
| RSA, SSL cookie | on | Per-context mutexes exist, but they are compiled out. |
| `gmtime` fallback | platform-dependent | `platform_util.c:189` uses the gmtime mutex. On POSIX builds the code uses `gmtime_r`, so the fallback mostly matters on non-POSIX targets. |

With the default config, sharing any of these between threads is a data race. Sharing a context such as an SSL session or DRBG between threads is also unsafe, even apart from the PSA global state.

**What would protect what, if you enable it**

Enabling `MBEDTLS_THREADING_C` plus `MBEDTLS_THREADING_PTHREAD` (or an ALT implementation) turns on the locks:

- **Global mutexes:** the PSA key-slot mutex, the PSA global-data mutex, the PSA RNG mutex, and the readdir and gmtime mutexes.
- **Per-object mutexes:** the DRBG and entropy contexts, RSA contexts, the SSL cache, the SSL cookie context, and the `memory_buffer_alloc` heap.

These protect the internal state of each object. They do not make a single object safe to use from two threads at once. Your application still has to avoid sharing TLS, X.509 or PK contexts across threads unless its own locking covers them.

**Doc requirement the default config misses**

The `MBEDTLS_THREADING_C` documentation (around `mbedtls_config.h:3740`) says you must enable it for any multithreaded use of PSA functions, for any TLS 1.3 connection regardless of configuration, and for any use of PSA-backed TLS/X.509/PK functions when `MBEDTLS_USE_PSA_CRYPTO` is on. The default config leaves it off, so a multithreaded application that uses the defaults is outside the documented safe configuration.

I checked the defaults and guards by reading the header and source. I did not build the library or run a threaded test.