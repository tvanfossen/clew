**Short answer:** with the default configuration, mbedtls runs no concurrent code of its own and takes no locks. Every mutex in the library sits behind `MBEDTLS_THREADING_C`, which is off by default.

**What is configured by default**

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`). `library/threading.c` compiles to nothing, so `mbedtls_mutex_lock/unlock` are never called.
- `MBEDTLS_PSA_CRYPTO_C` is on (line 3334), so the PSA global state and key-slot table exist, but nothing protects them.
- `MBEDTLS_ENTROPY_C` and `MBEDTLS_FS_IO` are on, so the per-context mutexes and the readdir mutex exist in the source but are compiled out.

**What runs concurrently**

The library creates no threads. The four spawn sites the index found are all in `programs/`:

| Site | Concurrency | Default build |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` (`pthread_create`) | one thread per TLS connection | refuses to build unless `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are set (line 24) |
| `programs/test/benchmark.c` (`TimerProc`, alarm) | timer thread | test/benchmark program only |
| `ssl_server2.c` and `benchmark.c` signal handlers | async signal context | these touch no mbedtls mutexes |

So by default, concurrency is whatever the application adds. If the application calls PSA, SSL, entropy or DRBG from more than one thread, nothing protects the shared state. `psa-thread-safety.md` says the same: correctness "out of the box" requires `MBEDTLS_PSA_CRYPTO_C` together with `MBEDTLS_THREADING_C`.

**What the mutexes protect (when `THREADING_C` is enabled, with pthread)**

| Mutex | Protects |
|---|---|
| `ctx->mutex` in `ctr_drbg`, `hmac_drbg`, `entropy`, `rsa`, `ssl_cache`, `ssl_ticket`, `ssl_cookie` | One object's state. It serializes calls on a single context and does nothing across contexts. |
| `mbedtls_threading_key_slot_mutex` | The PSA key-slot table, slot states and reader counts (`psa_crypto.c`, `psa_crypto_slot_management.c`) |
| `mbedtls_threading_psa_globaldata_mutex` | Non-RNG `global_data` fields and `psa_crypto_init` |
| `mbedtls_threading_psa_rngdata_mutex` | Built-in PSA RNG state (`psa_crypto_random.c`) |
| `mbedtls_threading_readdir_mutex` | `readdir`, used by `x509_crt.c` directory loading |
| `mbedtls_threading_gmtime_mutex` | The `gmtime` fallback in `platform_util.c`, only when no `gmtime_r` is available |
| `heap.mutex` in `memory_buffer_alloc.c` | The global heap allocator |

Per-object mutexes don't protect TLS sessions. The docs say TLS contexts must not be shared across threads.

**What stays unprotected even with threading on**

- The PSA guarantees cover key-management calls only. Other PSA functions are untested under concurrency.
- Driver entry points get no protection from the core, and a key in use can still be destroyed.
- `mbedtls_psa_crypto_free` must run after all threads finish.
- With `MBEDTLS_PSA_CRYPTO_EXTERNAL_RNG`, thread-safety of the RNG is the external implementation's responsibility.

**Caveat on the index:** the lock layer returned one identity, `mutex->mutex` in `threading.c`. Member-expression locks such as `ctx->mutex` aren't modelled, so the per-context table above comes from grep rather than the index.