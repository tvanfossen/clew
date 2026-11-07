**Short answer:** in the default configuration, the library runs no threads of its own, and none of its mutex code is compiled in. Concurrency exists only if the application calls into the library from several threads, and nothing protects the library in that case.

**Why the mutexes are inert by default**

- `MBEDTLS_THREADING_C` is not enabled in `include/mbedtls/mbedtls_config.h`. The only uncommented thread-related define is the `MBEDTLS_PSA_CRYPTO_C` family, and `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are both commented out (lines 2185, 2196).
- `library/threading.c` is wrapped in `#if defined(MBEDTLS_THREADING_C)` (line 18). The pthread backend (`threading_mutex_lock_pthread` etc.) only exists under `MBEDTLS_THREADING_PTHREAD`, and the function pointers `mbedtls_mutex_lock` and friends are defined there.
- Every call site I checked is guarded by the same macro, so with the default config the locks are never taken.

**What runs concurrently by default**

- Index thread inventory: 4 spawn sites, all first-party, all in `programs/` (`ssl_pthread_server.c:277`, `benchmark.c:430/444`, `ssl_server2.c:1699`). None are in `library/`. These are sample and test programs, plus signal and alarm handlers.
- So the library itself is single-threaded. Its internal state is only at risk when the application calls it from more than one thread, or from a signal handler or timer. The index can only see the spawn primitives its pattern set covers, so this is a claim about what it can see, not a proof that no other spawn mechanism exists.

**What the locks protect when `MBEDTLS_THREADING_C` is enabled**

| Lock | Protects | Where |
|---|---|---|
| `psa_key_slot_mutex` (global) | PSA key slot table: create, open, close, destroy, purge | `psa_crypto_slot_management.c`, `psa_crypto.c` |
| `psa_globaldata_mutex` (global) | PSA global driver and initialisation state | `psa_crypto.c:141-165`, `psa_crypto_slot_management.c:200` |
| `psa_rngdata_mutex` (global) | PSA RNG state | `psa_crypto.c:131`, `psa_crypto_random.c:147` |
| `readdir_mutex` (global) | `readdir()` in `x509_crt` directory parsing | `x509_crt.c:1611-1660` |
| `gmtime_mutex` (global) | `gmtime()` only when there is no thread-safe `gmtime_r` | `platform_util.c:189-201` |
| `heap.mutex` | The `memory_buffer_alloc` heap | `memory_buffer_alloc.c:544-562` |
| per-context `ctx->mutex` | One object: CTR_DRBG, HMAC_DRBG, entropy, RSA, SSL cache, SSL ticket, SSL cookie | the respective `.c` files |

Per-context mutexes protect a single object from concurrent use, not the whole library. Global mutexes protect shared process state. With `MBEDTLS_THREADING_C` off, the PSA global state, the heap and the RNG are all unprotected.

**Caveats**

- The lock index returned one identity, `mutex->mutex` in `threading.c`, because it does not resolve the spelling of the global and per-context mutexes. The table above comes from reading the call sites, not from that query.
- `threading.c` defines the default pthread backend as the only built-in backend. Supplying your own through `MBEDTLS_THREADING_ALT` requires `mbedtls_threading_set_alt()` to be called before any other use.
- I did not check whether the library's `psa_crypto` global-state code has any lock-free paths, nor whether ISR-context code paths exist. Both are outside what I verified.