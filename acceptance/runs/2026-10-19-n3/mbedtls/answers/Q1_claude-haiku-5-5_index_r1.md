**Short answer:** in the default configuration the library has no mutexes and creates no threads. Any concurrency comes from the application, and the library gives it no synchronization. The mutex and thread code only matters once you enable `MBEDTLS_THREADING_C` (plus a backend such as `MBEDTLS_THREADING_PTHREAD`).

**Why nothing is compiled in by default**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, and line 2196 has `//#define MBEDTLS_THREADING_PTHREAD`. Both are off.
- The whole body of `library/threading.c` is inside `#if defined(MBEDTLS_THREADING_C)` (line 18). With the default config it compiles to nothing, so the pthread wrappers, the function pointers and the global mutexes don't exist.
- Every mutex call site in `library/` is also gated on `MBEDTLS_THREADING_C`. That includes `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `rsa.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, `psa_crypto.c`, `psa_crypto_slot_management.c`, `psa_crypto_random.c`, `x509_crt.c`, `platform_util.c` and `memory_buffer_alloc.c`.
- `MBEDTLS_PSA_CRYPTO_C` *is* on by default (line 3334), so PSA runs without any of its locks.

**What runs concurrently**

- **The library itself:** nothing. The library never calls `pthread_create` or equivalent. The index's thread search finds four spawn sites, all in `programs/`: `ssl_pthread_server.c:277` (sample server), `benchmark.c:430` and `:444` (timer and alarm, test tool), and `ssl_server2.c:1699`, a signal handler.
- **The application:** any thread it runs. If two threads call into mbedtls on shared state (an `mbedtls_ssl_context`, a DRBG context, the PSA key store, the global RNG) without their own locking, that is a data race. The default build does not prevent it.
- **Signal handlers:** these count as asynchronous contexts. Code in the library is not written to be signal-safe.

**What is protected when `MBEDTLS_THREADING_C` is enabled**

| Mutex | Protects |
|---|---|
| Per-object `ctx->mutex` in `entropy`, `ctr_drbg`, `hmac_drbg`, `rsa`, `ssl_cache`, `ssl_cookie`, `ssl_ticket` | That one context's internal state, locked around each operation |
| `mbedtls_threading_key_slot_mutex` | The PSA key-slot table, in `psa_crypto_slot_management.c` and `psa_crypto.c` |
| `mbedtls_threading_psa_globaldata_mutex` | Global PSA state, in `psa_crypto.c` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state, in `psa_crypto_random.c` and `psa_crypto.c` |
| `mbedtls_threading_readdir_mutex` | `readdir()` use in `x509_crt` path loading (when `MBEDTLS_FS_IO` is on) |
| `mbedtls_threading_gmtime_mutex` | `gmtime_r` fallback in `platform_util.c` (only when the platform lacks a thread-safe `gmtime_r`) |

The index shows only one lock identity in the library, `mutex->mutex` in `threading.c`, with low confidence. It can't tell the global mutexes apart from the per-context ones because they are reached through member expressions.

**Gotchas**

- Enabling `MBEDTLS_THREADING_ALT` without calling `mbedtls_threading_set_alt()` makes every lock return `MBEDTLS_ERR_THREADING_BAD_INPUT_DATA` (`threading.c:127-128`). The failure shows up on the first lock call, not at build time.
- The locks are plain (non-recursive) pthread mutexes. Re-entering a locked path from the same thread deadlocks.
- The library's own locks cover only the state they guard. Sharing one `mbedtls_ssl_context` across threads is still the application's problem, and the config doc says so (`mbedtls_config.h:1877-1881`).

I did not verify the locking at runtime. These conclusions come from grepping the `#if` gates, reading `threading.c`, and the index's thread and lock queries.