**Short answer:** in the default configuration, the mutex code is compiled out. The library creates no threads, so nothing inside mbedtls runs concurrently. Any concurrency comes from your application calling into the library from several threads, and nothing protects the library's shared state.

**Why the mutexes are inactive.** `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`). `MBEDTLS_THREADING_ALT` and `MBEDTLS_THREADING_PTHREAD` are also commented out (lines 2185 and 2196). Every `mbedtls_mutex_lock/unlock` call site is wrapped in `#if defined(MBEDTLS_THREADING_C)`, and `library/threading.c:18` guards the whole file the same way. Only `configs/config-thread.h` and the `ssl_pthread_server` example turn it on. Nothing in `library/` or `include/` calls `pthread_create`.

**What is shared state, and what would protect it when threading is on:**

| Global | Defined in | Protected by (when `MBEDTLS_THREADING_C` is on) |
|---|---|---|
| PSA `global_data` (init flags, RNG state, subsystem state) | `library/psa_crypto.c:124` | `mbedtls_threading_psa_globaldata_mutex` |
| PSA RNG context and seed state | `psa_crypto.c`, `psa_crypto_random.c` | `mbedtls_threading_psa_rngdata_mutex` |
| PSA key slot table and key deletion | `psa_crypto.c` (destroy path), `psa_crypto_slot_management.c` | `mbedtls_threading_key_slot_mutex` |
| `readdir()` use in X.509 directory loading | `x509_crt.c:1611` | `mbedtls_threading_readdir_mutex` (only when `MBEDTLS_FS_IO`) |
| Non-reentrant `gmtime()` fallback | `platform_util.c:189` | `mbedtls_threading_gmtime_mutex` (only when `THREADING_USE_GMTIME`) |

The per-object rule is in the public headers. `entropy.h`, `ssl_cache.h`, `ssl_ticket.h` and `ssl_cookie.h` say they are thread-safe only if `MBEDTLS_THREADING_C` is enabled. The `mbedtls_config.h` doc block at line 3740 lists the cases where you must enable it: any PSA call from more than one thread, TLS/X.509/PK calls when `MBEDTLS_USE_PSA_CRYPTO` is on, and TLS 1.3 connections regardless of configuration.

**Default build, concretely.** `MBEDTLS_PSA_CRYPTO_C`, `MBEDTLS_FS_IO` and `MBEDTLS_PLATFORM_C` are on by default, so the PSA global state, key slots and RNG exist and are used. Without `MBEDTLS_THREADING_C` they are accessed unlocked. The `readdir` and `gmtime` mutexes are compiled out with it. So a multithreaded application using default settings gets no internal locking. It has to serialize all access itself, including `psa_crypto_init()`, or enable `MBEDTLS_THREADING_C` with `MBEDTLS_THREADING_PTHREAD` (or `MBEDTLS_THREADING_ALT` on bare metal).

**Caveats:**
- I read this from the source and did not build or run anything, so the default-enabled set is from the `mbedtls_config.h` lines above, not a preprocessed build.
- I did not check whether TLS 1.3 is compiled in by default. If it is, the header's "TLS 1.3 always needs threading" note applies to the default build too.