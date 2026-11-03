**Short answer:** in the default configuration, nothing in mbedtls is protected by a mutex, and the library assumes one thread at a time touches any given context or the PSA global state. The mutex layer is compiled out.

**Why the mutex layer is off.** `include/mbedtls/mbedtls_config.h` has `//#define MBEDTLS_THREADING_C` (line ~3787), and `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are both commented out. `MBEDTLS_USE_PSA_CRYPTO` is also not defined by default. Every `mbedtls_mutex_lock` call sits inside `#if defined(MBEDTLS_THREADING_C)`, so the default build has no locks anywhere. The header's own docs say the library "assumes it is used in a non-threaded environment or that contexts are not shared between threads."

**What runs concurrently.** The library creates no threads. `pthread_create` appears only in `programs/ssl/ssl_pthread_server.c`, which is an example. Concurrency therefore only happens if the application calls the library from several threads. The default build gives no protection for that.

**What is unprotected by default, and what the code would otherwise guard:**

| Shared state | Protected by (only when `THREADING_C` is on) | Default build |
|---|---|---|
| PSA global state (`static psa_global_data_t global_data` in `psa_crypto.c:124`: init flags, RNG state) | No dedicated lock here; `mbedtls_threading_psa_globaldata_mutex` is used around some paths in `psa_crypto.c` (~8488–8537) | Unlocked. `psa_crypto_init()` and the subsystem flags race. |
| PSA key slots and persistent-key deletion | `mbedtls_threading_key_slot_mutex` (`psa_crypto_slot_management.c`, around line 814–1090) | Unlocked. Two threads can destroy or reload the same key. |
| PSA RNG reseed after `fork` (`psa_crypto_random.c:146`) | `mbedtls_threading_psa_rngdata_mutex` | Unlocked. |
| `mbedtls_entropy_context` (`entropy.c`) | per-context `ctx->mutex` | Unlocked, so one entropy context must not be shared. |
| SSL session cache (`ssl_cache.c`), ticket keys (`ssl_ticket.c`), cookie secrets (`ssl_cookie.c`) | per-object mutexes | Unlocked. |
| `gmtime` fallback (`threading.c`, `THREADING_USE_GMTIME`) | `mbedtls_threading_gmtime_mutex` | Only used when the platform lacks `gmtime_r`. On Linux, `platform_util.c:184` uses `gmtime_r`, which is reentrant, so no lock is needed. |

**What the default does protect.** Per-object state is safe only if each object is confined to one thread at a time. That covers the usual pattern: one `mbedtls_ssl_context` per connection, with its own config and RNG. Nothing in the default build makes shared contexts safe.

**The gap to watch.** `MBEDTLS_PSA_CRYPTO_C` is on by default (`mbedtls_config.h:3334`), so the PSA global state is always present. If an application calls PSA functions from more than one thread without enabling `MBEDTLS_THREADING_C`, that is an unsynchronized race. The config comments say this explicitly: enable `MBEDTLS_THREADING_C` plus `MBEDTLS_THREADING_PTHREAD` (or `_ALT`) for any multithreaded use. The docs also list TLS 1.3 connections as needing it "regardless of the compile-time configuration."

**Not verified:** I did not build the library or run any concurrency test, so the claims above come from reading the source. The `global_data` race is an inference from the absence of locks around its accesses, not a reproduced failure.