**Short answer:** in the default configuration, the library creates no threads and takes no locks. Nothing inside mbedtls is concurrent with itself. The only concurrency is the application's own threads, and nothing protects shared state between them. One part of the default build is still shared state: PSA.

**Default configuration**

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`), so every mutex call site is compiled out. Those are the `#if defined(MBEDTLS_THREADING_C)` blocks throughout `library/`.
- No `pthread_create`, `CreateThread` or `std::thread` appears anywhere in `library/` or `include/`.
- `MBEDTLS_PSA_CRYPTO_C` is on by default (line 3334), and PSA keeps implicit process-wide state. The config header's own note (around line 3740) says that if more than one thread may use any PSA function, you must enable `MBEDTLS_THREADING_C`.

So a multithreaded application on the default build is racing on:

| Shared state | Where | Protected by (only if THREADING_C is on) |
|---|---|---|
| PSA global init flags and subsystem state | `library/psa_crypto.c` `global_data` | `mbedtls_threading_psa_globaldata_mutex` |
| PSA RNG state and fork-reseed | `psa_crypto.c`, `psa_crypto_random.c` | `mbedtls_threading_psa_rngdata_mutex` |
| PSA key slots (register/unregister, read counts) | `psa_crypto.c` (`psa_unregister_read_under_mutex`), `psa_crypto_slot_management.c` | `mbedtls_threading_key_slot_mutex` (plus globaldata for `key_slots_initialized`) |
| Entropy pool | `library/entropy.c` | per-context `ctx->mutex` |
| SSL session cache, session tickets | `library/ssl_cache.c`, `library/ssl_ticket.c` | per-context mutex |
| `gmtime` fallback buffer | `library/platform_util.c` | `mbedtls_threading_gmtime_mutex`, only on the `PLATFORM_UTIL_USE_GMTIME` path; POSIX builds with `gmtime_r` skip it |

Entropy is on by default (`MBEDTLS_ENTROPY_C`, line 2895), so a single `mbedtls_entropy_context` shared between threads is also unprotected by default.

**When THREADING_C is enabled**

- With `MBEDTLS_THREADING_PTHREAD`, the lock functions are pthread mutexes (`library/threading.c`).
- With `MBEDTLS_THREADING_ALT`, the function pointers default to dummy/fail stubs until the application calls `mbedtls_threading_set_alt()`. Until then, locks return `MBEDTLS_ERR_THREADING_BAD_INPUT_DATA`.
- The mutexes protect the state in the table above. They do not make a single context safe to use from two threads at once. The docs still require the application to avoid sharing a context unless it does its own locking.

**Gaps I did not resolve**

- I did not check whether `MBEDTLS_USE_PSA_CRYPTO` is on by default, so I cannot say for certain that TLS and X.509 calls reach PSA in the default build.
- `mbedtls_threading_readdir_mutex` is defined and initialised in `threading.c`, but no `library/*.c` file takes it. Any user is outside the library.
- The only in-tree multithreaded example is `programs/ssl/ssl_pthread_server.c`, which is not part of the library build.

A PostToolUse hook message after one of my reads suggested switching to the clew `dossier` tool. I did not need it for this question, so I answered from the source.