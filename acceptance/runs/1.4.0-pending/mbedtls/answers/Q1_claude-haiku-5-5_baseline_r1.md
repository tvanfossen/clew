**Short answer:** in the default configuration the library creates no threads and takes no locks. Any concurrency comes from the application's own threads calling into the library, and nothing inside mbedtls protects shared state from them. The one piece of shared state that matters, the PSA global data, is unprotected by default.

**Why:** `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787`, and `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also off (lines 2185, 2196). `library/threading.c` is wrapped entirely in `#if defined(MBEDTLS_THREADING_C)`, so the mutex globals and the pthread wrapper are never compiled. No CMake or Makefile default turns it on.

**What is enabled by default, and whether it locks:**

| Component (default) | Shared state | Protection by default |
|---|---|---|
| `MBEDTLS_PSA_CRYPTO_C` (on) | Static `global_data` for key slots and the RNG, `library/psa_crypto.c:124` | None. Every lock is `#if MBEDTLS_THREADING_C`. |
| `MBEDTLS_ENTROPY_C` (on) | Entropy pool, `entropy.c` | None. Mutex is compiled out. |
| `MBEDTLS_SSL_CACHE_C` / `MBEDTLS_SSL_TICKET_C` (on) | Session cache and ticket keys | None. |
| `MBEDTLS_CTR_DRBG_C` / HMAC_DRBG (on) | Per-context DRBG state | None. Same as entropy. |
| `x509_crt.c` readdir, `platform_util.c` gmtime | Shared static mutexes | Not compiled in. The gmtime fallback only applies with `PLATFORM_UTIL_USE_GMTIME`; on POSIX it calls `gmtime_r`, which is already thread-safe. |
| `MBEDTLS_USE_PSA_CRYPTO` | Off by default | Not applicable. |

**Practical consequences:**
- Each context (SSL, cipher, DRBG, entropy, cache, ticket) may be used by only one thread at a time, unless the application adds its own lock.
- Calling `psa_crypto_init()`, or any PSA function, from two threads at once is a data race on `global_data`. The header comment at `mbedtls_config.h:3314` says this explicitly.
- The `psa_crypto` RNG state is shared and unprotected, so two threads using random generation can race on it.
- Sharing one `ssl_cache` or `ssl_ticket` context between server threads is unsafe unless `MBEDTLS_THREADING_C` is enabled.

**To make it safe for multithreaded use:** enable `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` (on POSIX) or `MBEDTLS_THREADING_ALT`, and call `psa_crypto_init()` before spawning threads. The header says this is required whenever more than one thread calls PSA or any TLS/X.509 API with `MBEDTLS_USE_PSA_CRYPTO` enabled. Note that `check_config.h:995-1010` enforces that exactly one of the two implementations is chosen.

**Caveat:** I read the defaults from `mbedtls_config.h` and the build files; I did not compile the library or run a threaded test. The `configs/` variants may enable threading, but they are not the default.