**Short answer:** with the default configuration, mbedtls takes no mutexes and starts no threads. Every lock in the library is compiled out, so nothing inside the library is protected against concurrent callers. Any sharing across threads is the application's job to serialize.

**Why the default is lock-free**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`).
- Every mutex use in `library/` sits behind `#if defined(MBEDTLS_THREADING_C)`. That includes `threading.c` itself, which is wrapped in one guard (line 18 to 94).
- The index is misleading here. Its configured macros are `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD`, set by flag for this build, so its lock and thread layers describe a threaded variant, not the default. I read the default from the header and the guards.

**What runs concurrently**

- The library spawns no threads. The four spawn sites the index found are all in `programs/`: `ssl_pthread_server.c:277` (one pthread per connection), `ssl_server2.c:1699` (signal handler), and `benchmark.c` (alarm timer and handler).
- Library code runs on whatever threads the caller uses. Under the default build, two threads that share a context race on it.

**What the mutexes protect when `MBEDTLS_THREADING_C` is on**

| Lock | Protects | Where |
|---|---|---|
| per-context `ctx->mutex` in CTR_DRBG and HMAC_DRBG | DRBG internal state during generate and reseed | `ctr_drbg.c:702`, `hmac_drbg.c:387` |
| `cache->mutex` | SSL session cache entries (get, set, remove) | `ssl_cache.c:83`, `:258`, `:330` |
| `ctx->mutex` | SSL ticket key use during ticket write and parse | `ssl_ticket.c:329`, `:444` |
| entropy context mutex | entropy source gathering | `entropy.c` guarded blocks |
| `mbedtls_threading_key_slot_mutex` | PSA key slot table | `psa_crypto.c`, `psa_crypto_slot_management.c` |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global data | `psa_crypto.c:141-165` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG reseed and generate | `psa_crypto.c:8030-8037` |
| `mbedtls_threading_gmtime_mutex` | `gmtime()`, which is not thread-safe | `platform_util.c:189-201` |
| `mbedtls_threading_readdir_mutex` | directory reads in X.509 CRT loading | `x509_crt.c:1611-1660` |

The global mutexes are declared in `threading.c:182-188`. Each one is initialised and freed only when its feature is enabled.

**Other things to know**

- The lock functions are function pointers (`threading.c`), defaulting to pthread. `MBEDTLS_THREADING_ALT` replaces them. The pointers are plain globals, so switching implementations is unsynchronised and should happen before any threads start.
- The memory-buffer allocator's mutexed wrappers exist only with `MBEDTLS_MEMORY_BUFFER_ALLOC_C`, which is off by default (`mbedtls_config.h:3076`).
- The index reports no nested two-lock holdings. That is an empty result for this build, not proof of deadlock freedom.
- The session cache is on by default (`MBEDTLS_SSL_CACHE_C`), but its mutex is not. A default build that shares one cache across threads has no protection.