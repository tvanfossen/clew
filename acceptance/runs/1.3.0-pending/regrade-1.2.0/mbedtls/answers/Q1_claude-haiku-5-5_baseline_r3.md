**Short answer:** with the default configuration, the library starts no threads and takes no locks. Mutex code is compiled out, so any concurrency is whatever the application creates, and nothing in the library protects shared state from it.

**Why the locks are off by default**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`). Neither `MBEDTLS_THREADING_PTHREAD` nor `MBEDTLS_THREADING_ALT` is enabled either (lines 2185, 2196).
- Every `mbedtls_mutex_lock`/`unlock` call site is wrapped in `#if defined(MBEDTLS_THREADING_C)`. That covers `ssl_cache.c`, `ssl_ticket.c`, `entropy.c`, `psa_crypto.c`, `psa_crypto_random.c` and `psa_crypto_slot_management.c`, which I checked.
- `library/` contains no `pthread_create`, `std::thread` or `_beginthread`. The library never creates a thread.
- The header's own comment says the library "traditionally assumes it is used in a non-threaded environment or that contexts are not shared between threads."

**What the application can run concurrently, and what is unprotected**

| Shared state | Default (`THREADING_C` off) | With `THREADING_C` on |
|---|---|---|
| Session cache (`ssl_cache.c`, `mbedtls_ssl_cache_context.mutex`) | Unprotected | Mutex guards cache entries |
| Session-ticket keys (`ssl_ticket.c`, `ctx->mutex`) | Unprotected | Mutex guards keys and rotation |
| Entropy context (`entropy.c`, `ctx->mutex`) | Unprotected | Mutex guards the source list and accumulator |
| PSA RNG state and fork reseed (`psa_crypto_random.c`, `rngdata` mutex) | Unprotected | Mutex guards RNG state |
| PSA init flags (`psa_crypto.c`, `globaldata` mutex) | Unprotected | Mutex guards initialization state |
| PSA key-slot table and reader counts (`psa_crypto_slot_management.c`, global key slot mutex) | Unprotected | Mutex guards slots |

The PSA state is a single process-wide `global_data` in `psa_crypto.c`, so PSA is effectively a shared context. Two threads calling any `psa_*` function at once race on it by default. The rule that PSA is shared applies whether or not you use the TLS layer on top.

**Concretely, under the default config**

- Two threads sharing one `mbedtls_ssl_cache_context` or one ticket context can corrupt it.
- Two threads calling PSA concurrently, including through TLS when `MBEDTLS_USE_PSA_CRYPTO` is on, can race on key slots and initialization.
- Separate contexts used one-per-thread are safe as far as the library goes, since nothing global is touched. The PSA global state is the exception.
- The one process-level concurrency the library handles without a mutex is `fork()`. `psa_random_internal_generate` checks `getpid()` against a stored pid and reseeds the RNG in a child. With `THREADING_C` off, that reseed is not locked, but it only matters if the parent and child run concurrently on the same state.

**Caveat:** the config docs say a TLS 1.3 connection requires `MBEDTLS_THREADING_C` "regardless of the compile-time configuration" (`mbedtls_config.h`, the `MBEDTLS_THREADING_C` block). I took that as written and did not trace which code path makes it necessary. If you run TLS 1.3 in a multi-threaded program, enable the threading layer anyway.

To make the default safe for multi-threaded use, set `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`. The `check_config.h` checks at lines 995–1008 enforce that pairing at build time.