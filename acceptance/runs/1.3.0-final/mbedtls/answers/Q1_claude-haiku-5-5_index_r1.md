**Short answer:** in the default configuration, the library runs no concurrency of its own and protects nothing with mutexes. Any concurrency comes from the application, and the threads in this repo live only in example and test programs.

**Why the default is single-threaded**

`MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`), and `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also commented out (lines 2196 and 2185). Every mutex use in the library sits behind `#if defined(MBEDTLS_THREADING_C)`, so none of it compiles. The header's own comment says Mbed TLS "traditionally assumes it is used in a non-threaded environment." `MBEDTLS_PSA_CRYPTO_C` is on by default (line 3334), so the PSA global state is present but unlocked.

**What runs concurrently**

```
Default build (THREADING_C off)
  library/   -> no threads, no locks; all shared state unguarded
  caller app -> may run N threads; must serialise access itself

Example/test programs (not part of the library)
  programs/ssl/ssl_pthread_server.c   handle_ssl_connection  pthread per client (needs THREADING_C + PTHREAD)
  programs/ssl/ssl_server2.c          term_handler           SIGTERM handler, sets received_sigterm
  programs/test/benchmark.c           sighandler / TimerProc  alarm signal and Win32 timer
```

The index found four spawn sites, all in `programs/`, and none in `library/`. The pthread server is the only real multi-threaded example. Its thread function is gated on `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD`, which are both off by default, so it does not build under the defaults either. The two signal handlers run asynchronously in the example programs.

**What the locks protect when threading is enabled**

The library's protection, as the code and `docs/architecture/psa-thread-safety/psa-thread-safety.md` describe it:

| Guarded state | Mutex | Where |
|---|---|---|
| PSA key store (key slots, state, reader counts) | `mbedtls_threading_key_slot_mutex` | `psa_crypto_slot_management.c`, `psa_crypto.c` |
| PSA `global_data` in `psa_crypto.c`, and `key_slots_initialized` | `mbedtls_threading_psa_globaldata_mutex` | `psa_crypto.c` |
| PSA RNG state | `mbedtls_threading_psa_rngdata_mutex` | `psa_crypto_random.c`, `psa_crypto.c` |
| `gmtime()` result | `mbedtls_threading_gmtime_mutex` | `platform_util.c` |
| `readdir` in X.509 path loading | `mbedtls_threading_readdir_mutex` | `x509_crt.c` |
| Per-context state (entropy, CTR-DRBG, HMAC-DRBG, RSA, SSL cache, cookie, ticket) | a `mutex` field in each context | `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `rsa.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c` |
| Heap (`memory_buffer_alloc`) | `heap.mutex` | `memory_buffer_alloc.c` |

Three limits matter:

- **PSA is only partly thread-safe.** The doc says the 3.6 work covers key management and `psa_crypto_init`. Other PSA functions are "not currently tested." Driver entry points "may be called concurrently," and destroying a key that is in use is not guarded. `mbedtls_psa_crypto_free` must run on one thread after all others finish.
- **The RNG is not fully covered.** The doc says `mbedtls_psa_random_free` is not thread-safe, and `mbedtls_psa_random_init` and `_seed` are safe only while the caller holds the RNG mutex. The RNG fields are not protected by the global-data mutex.
- **The per-context mutexes protect only that context.** The library does not make a shared context safe unless the caller also uses the context from one thread at a time. The `MBEDTLS_THREADING_C` doc comment says this too.

**Caveats on the tooling**

The lock inventory is not a full map. The index reports one lock identity, `mutex->mutex` in `library/threading.c`, because it does not model the global mutex operands as identities. I got the table above from grepping the call sites and reading the doc, not from the index's lock layer. Where I say a guard exists, I checked the call site. I did not verify every acquire/release pair for ordering or deadlock freedom. The doc claims the PSA key-management locking is deadlock-free but gives no proof.