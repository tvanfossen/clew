**Short answer: with the default configuration, nothing in mbedtls runs concurrently inside the library, and no mutex is compiled in.**

**Why the mutexes are absent by default**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`).
- Both backends are also off: `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185).
- Every mutex call site in the library sits behind `#if defined(MBEDTLS_THREADING_C)`. Those blocks compile to nothing in the default build.
- `library/threading.c` is guarded by the same macro (line 18), so the function-pointer table (`mbedtls_mutex_lock` and friends, line 103) does not exist either.

**What does run concurrently**

The index found four thread spawn sites, all in `programs/`, none in `library/`:

| Spawn site | Kind | Role |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | pthread | Example server, one thread per connection |
| `programs/test/benchmark.c:430` | win32 timer | Alarm timer |
| `programs/test/benchmark.c:444` | signal handler | Alarm |
| `programs/ssl/ssl_server2.c:1699` | signal handler | Termination handler |

The library itself creates no threads. Concurrency comes only from the caller, for example one thread per TLS connection in the example server. The library then runs on whatever threads the application gives it, unprotected.

**What would be protected if you enabled `MBEDTLS_THREADING_C` plus a backend**

The mutex call sites I found by grep, grouped by what they guard:

- **PSA global state** (`library/psa_crypto.c`, lines ~130–166, 1305, 1800–1927, 2018, 8029–8055): separate mutexes for the RNG data (`mbedtls_threading_psa_rngdata_mutex`), the global initialisation flags (`mbedtls_threading_psa_globaldata_mutex`), and the key slot table (`mbedtls_threading_key_slot_mutex`, line 2022). PSA is on by default (`MBEDTLS_PSA_CRYPTO_C` at line 3334), so this is the most important one.
- **Per-object state**: the DRBG and entropy contexts (`library/ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`) each take a mutex around their own state.
- **Shared TLS caches**: `library/ssl_cache.c` locks `cache->mutex` around session entries, and `library/ssl_ticket.c` locks `ctx->mutex` around ticket keys.
- **Allocator**: `library/memory_buffer_alloc.c` guards its heap.

**Important caveats**

- Default builds enable `MBEDTLS_SSL_CACHE_C` (line 3670) and `MBEDTLS_SSL_TICKET_C` (line 3693). Their mutex code is compiled out too. If you share one session cache or ticket context across threads in a default build, nothing protects it.
- The docs say the same thing. The `MBEDTLS_THREADING_C` description (`mbedtls_config.h` ~3740) requires enabling it for any multithreaded use of PSA, of TLS/X.509/PK when PSA is in use, or of a shared context.
- The index reported one lock identity (`mutex->mutex` in `library/threading.c`) and zero two-lock nestings. That reflects the indexer only recognising the wrapper function, not the PSA globals. I relied on grep for the mutex call sites above.