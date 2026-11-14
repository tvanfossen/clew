**Short answer:** with the default `include/mbedtls/mbedtls_config.h`, the library runs no threads of its own and contains no mutexes. Every lock in the tree sits behind `#if defined(MBEDTLS_THREADING_C)`, and that macro is commented out (`mbedtls_config.h:3787`: `//#define MBEDTLS_THREADING_C`). The only concurrency is whatever the application does by calling the library from several threads, and nothing protects shared state from that.

**What is compiled out by default**

- `library/threading.c` is wrapped in `#if defined(MBEDTLS_THREADING_C)`, so the global mutexes and the pthread wrapper are not built.
- `MBEDTLS_THREADING_PTHREAD` (`:2196`) and `MBEDTLS_THREADING_ALT` (`:2185`) are also commented out. `check_config.h:995-1009` makes both require `MBEDTLS_THREADING_C`.
- Every per-context lock is compiled out too: `ctr_drbg.c`, `entropy.c`, `hmac_drbg.c`, `rsa.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, and `memory_buffer_alloc.c`'s heap lock.

**What is enabled by default but unprotected**

The default build turns on `MBEDTLS_ENTROPY_C`, `MBEDTLS_CTR_DRBG_C`, `MBEDTLS_PSA_CRYPTO_C`, `MBEDTLS_SSL_CACHE_C`, and `MBEDTLS_FS_IO` (`:2895`, `:2757`, `:3334`, `:3670`, `:1186`). Their shared state has no lock. If two threads use one entropy or DRBG context, one SSL session cache, or one PSA key store, that is a data race. The PSA key-slot and RNG code only takes its mutexes under `#if defined(MBEDTLS_THREADING_C)`, so none of those paths run either.

**What the locks would protect if you enabled `MBEDTLS_THREADING_C` plus a backend (`MBEDTLS_THREADING_PTHREAD` or `ALT`)**

| Mutex | Protects |
|---|---|
| `mbedtls_threading_psa_globaldata_mutex` | Global PSA data; per-slot reader/writer state |
| `mbedtls_threading_key_slot_mutex` | Key destruction (`PENDING_DELETION` handling) |
| `mbedtls_threading_psa_rngdata_mutex` | Built-in PSA RNG state |
| `mbedtls_threading_readdir_mutex` | `readdir()` in `x509_crt` path loading (`MBEDTLS_FS_IO`) |
| `mbedtls_threading_gmtime_mutex` | `gmtime()` fallback, only when `gmtime_r` is unavailable |
| Per-object `mutex` | Entropy, CTR_DRBG, HMAC_DRBG, RSA, SSL cache, cookie, ticket, heap |

**Caveats**

- `docs/architecture/psa-thread-safety/psa-thread-safety.md:3` says PSA calls are not thread-safe in general. Thread-safe key management and `psa_crypto_init` arrived in 3.6, and only with `MBEDTLS_PSA_CRYPTO_C` plus `MBEDTLS_THREADING_C`.
- I read the default header and the `threading.c`/`check_config.h` guards, but I did not build the library or run a test. I only checked the first 40 lines of `configs/config-thread.h`, so I have not confirmed whether that preset enables `MBEDTLS_THREADING_C`.