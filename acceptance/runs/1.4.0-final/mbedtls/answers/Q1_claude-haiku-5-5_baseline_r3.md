**Short answer:** by default, nothing inside mbedtls runs concurrently, and nothing is protected by a mutex. `MBEDTLS_THREADING_C` is commented out in the default config (`include/mbedtls/mbedtls_config.h:3787`, `//#define MBEDTLS_THREADING_C`). With it off, `library/threading.c` compiles to nothing, and every `mbedtls_mutex_*` call site is wrapped in `#if defined(MBEDTLS_THREADING_C)`. The library therefore has no internal concurrency. Any thread safety is the caller's job: a context must not be shared across threads without external locking, and the PSA global state must not be touched from more than one thread.

**What changes when you turn it on** (`MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`):

| Protected object | Lock | Where |
|---|---|---|
| Per-context state for CTR_DRBG, HMAC_DRBG, entropy, RSA, SSL cache, SSL ticket, SSL cookie | `ctx->mutex`, initialised in each `*_init`/setup | `library/ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`, `rsa.c`, `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c` |
| PSA global init state and driver-wrapper flags | `mbedtls_threading_psa_globaldata_mutex` | `library/psa_crypto.c` (`psa_get_initialized`, etc.) |
| PSA RNG state | `mbedtls_threading_psa_rngdata_mutex` | `library/psa_crypto.c`, `library/psa_crypto_random.c` |
| PSA key slot table | `mbedtls_threading_key_slot_mutex` | `library/psa_crypto.c`, `library/psa_crypto_slot_management.c` |
| Heap for the buffer allocator | `heap.mutex` | `library/memory_buffer_alloc.c` (only if `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is on) |
| `gmtime()` (non-reentrant, only where the platform lacks `gmtime_r`) | `mbedtls_threading_gmtime_mutex` | `library/platform_util.c` |
| `readdir()` | `mbedtls_threading_readdir_mutex` | `library/threading.c` (under `MBEDTLS_FS_IO`) |

The per-context locks protect a single object shared by several threads. The PSA locks protect process-wide state, which is the reason the header says that PSA use from several threads requires `MBEDTLS_THREADING_C`, even when no context is shared.

**Caveats I'd check before relying on this:**

- The mutex calls are in library code, not a per-call contract. I read them in source and did not build or run a threaded test, so the table is from reading the code only.
- Some locks are taken with the return value ignored (e.g. `mbedtls_mutex_lock(&mbedtls_threading_psa_globaldata_mutex)` in `psa_get_initialized`). A failed lock then proceeds unprotected. The PSA-internal `PSA_THREADING_CHK_*` macros do check the return.
- The `ALT` path (`mbedtls_threading_set_alt`) calls the user-supplied mutex init from inside the library, and the default `MBEDTLS_THREADING_PTHREAD` is only one of the two backends. If you select neither, `check_config.h` rejects the config.
- The header says `MBEDTLS_THREADING_C` must also be on for TLS, X.509 and PK calls when `MBEDTLS_USE_PSA_CRYPTO` is enabled, and for any TLS 1.3 connection. So "default off" is only safe in a single-threaded program.

**Bottom line:** the shipped default is a single-threaded library with no locks at all. Enabling the threading layer adds per-object locks on shared contexts and the PSA global state, and that is the only concurrency protection the library provides.