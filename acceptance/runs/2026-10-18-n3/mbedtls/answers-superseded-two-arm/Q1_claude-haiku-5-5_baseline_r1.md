**Short answer:** with the default `mbedtls_config.h`, the library takes no locks, and nothing inside it creates threads. Any concurrency is the application's own. Every shared object is unprotected, so the application has to serialize access itself.

**Why:** the threading layer is off by default.

- `MBEDTLS_THREADING_C` is commented out at `include/mbedtls/mbedtls_config.h:3787`.
- `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also commented out.
- `library/threading.c` is wrapped in `#if defined(MBEDTLS_THREADING_C)`, so in the default build it compiles to nothing.
- Every `mbedtls_mutex_lock/unlock` call site in the library sits under `#if defined(MBEDTLS_THREADING_C)`. So in the default build there are no lock calls at all.
- `library/` has no `pthread_create` or thread creation. The only in-tree threaded code I found is the example `programs/ssl/ssl_pthread_server.c`, which the application runs, not the library.

**What is unprotected by default** (state the application must not share without its own locking):

| Object | Protected when `THREADING_C` is on |
|---|---|
| PSA global state (`global_data`, RNG state, key slots) in `psa_crypto.c`, `psa_crypto_slot_management.c`, `psa_crypto_random.c` | `psa_globaldata_mutex`, `psa_rngdata_mutex`, `key_slot_mutex` |
| `mbedtls_ctr_drbg_context`, `hmac_drbg`, `entropy` contexts | per-context `mutex` |
| `mbedtls_ssl_cache_context` (server session cache) | per-cache `mutex` |
| `mbedtls_ssl_ticket_context` | per-context `mutex` |
| `mbedtls_ssl_cookie_context` | per-context `mutex` |
| `rsa` contexts (blinding state) | per-context `mutex` |
| `memory_buffer_alloc` heap | `heap.mutex` |
| `x509_crt` directory reads (`readdir`) | global `readdir_mutex` |
| `gmtime` wrapper | global `gmtime_mutex` |

So in the default build, a session cache or ticket context shared across server threads, a shared DRBG, or concurrent PSA calls are all data races.

**Caveats:**

- Per-connection `mbedtls_ssl_context` objects are not shared state. Each connection is safe to run on its own thread, provided no other thread touches it.
- The header comment at `mbedtls_config.h:3740` is explicit that a PSA call from more than one thread requires `MBEDTLS_THREADING_C`. Enabling `MBEDTLS_USE_PSA_CRYPTO` (off by default, line 2230) pushes more of the library through PSA, so the requirement widens.
- Enabling `THREADING_C` alone is not enough. You must also select a backend, either `THREADING_PTHREAD` or `THREADING_ALT`. `check_config.h:995-1010` rejects `THREADING_C` without one. With `ALT`, the application must call `mbedtls_threading_set_alt()` before any other library call.
- I read the source and did not build or run anything, so the default-configuration claim rests on the config header and the `#if` guards, not a compiled check.