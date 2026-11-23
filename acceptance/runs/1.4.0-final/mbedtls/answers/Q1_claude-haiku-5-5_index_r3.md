**Short answer:** with the default configuration, the library runs no concurrent code of its own and takes no locks. Concurrency comes only from the application's threads, and the library's shared state is unprotected, so the caller must serialize access.

**Why:** the mutex layer is opt-in. In `include/mbedtls/mbedtls_config.h`, `MBEDTLS_THREADING_C` (line 3787), `MBEDTLS_THREADING_PTHREAD` (2196) and `MBEDTLS_THREADING_ALT` (2185) are all commented out. Every lock call in the library sits behind `#if defined(MBEDTLS_THREADING_C)`, so none is compiled in:

- `library/threading.c:18` gates the whole layer, including the pthread backend at line 50.
- `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `rsa.c`, `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c`, `x509_crt.c`, `memory_buffer_alloc.c`, `platform_util.c` (gmtime), and the PSA globals in `psa_crypto.c`, `psa_crypto_slot_management.c` and `psa_crypto_random.c` are all gated the same way.

The index's thread layer finds four spawn sites, all in `programs/` (`ssl_pthread_server.c:277`, `ssl_server2.c:1699`, `benchmark.c:430/444`). None is in `library/`. The lock layer reports one identity, `mutex->mutex` in `threading.c`. That undercounts, because it does not model member-expression locks like `ctx->mutex`; I confirmed those with a grep of `mbedtls_mutex_lock` call sites.

**What the locks protect when you enable `MBEDTLS_THREADING_C` plus `_PTHREAD`:**

| Lock | Protects |
|---|---|
| `ctx->mutex` in entropy, CTR_DRBG, HMAC_DRBG, RSA | One context's state during gather/random/public-op calls (`entropy.c:93,179,253`, `ctr_drbg.c:703`, `hmac_drbg.c:388`, `rsa.c:1239`) |
| `cache->mutex` in ssl_cache | The session cache table on get/remove (`ssl_cache.c:84,331`) |
| `heap.mutex` in memory_buffer_alloc | The heap free-list on calloc/free (`memory_buffer_alloc.c:544,558`) |
| `mbedtls_threading_psa_rngdata_mutex` | Global PSA RNG state: reseed, deplete, generate, prediction-resistance (`psa_crypto.c:8030–8077`, `psa_crypto_random.c:147`) |
| `mbedtls_threading_key_slot_mutex` | The PSA key slot table (`psa_crypto.c:2022`, `psa_crypto_slot_management.c:1034`) |
| `mbedtls_threading_psa_globaldata_mutex` | PSA driver/key-slot initialization flags (`psa_crypto.c:159`, `psa_crypto_slot_management.c:200`) |
| `mbedtls_threading_gmtime_mutex` | The `gmtime_r` fallback (`platform_util.c:189`) |

**Caveats:**

- Enabling the layer does not make the library thread-safe everywhere. Only the sites above lock. Any shared state outside them is still unprotected.
- The lock function pointers in `threading.c:101–104` are mutable. `mbedtls_threading_set_alt` (`threading.c:140`) reassigns them and must run before any thread starts.
- `MBEDTLS_THREADING_ALT` is also off by default. The `*_mutexed` and PSA global locks depend on the same layer, so they are off too.

I did not read every gated site in full (for example, the `x509_crt.c` locks), so the table lists the ones I checked.