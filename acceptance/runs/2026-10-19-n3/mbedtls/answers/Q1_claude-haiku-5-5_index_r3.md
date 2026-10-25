**Short answer:** in the default configuration, mbedtls runs no concurrency of its own and its mutexes are compiled out. The library is single-threaded by contract. Any concurrency comes from the application, and the library gives no protection against it.

**Why the mutexes are absent by default**

- The whole layer is gated on `MBEDTLS_THREADING_C`, and it is commented out in the default `include/mbedtls/mbedtls_config.h:3787`. `MBEDTLS_THREADING_PTHREAD` is also commented out (`:2196`), so no pthread backend is selected either.
- `library/threading.c` wraps everything in `#if defined(MBEDTLS_THREADING_C)` (line 18), so with the default config it contributes nothing.
- The index reports `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` as configured macros, but that is because this index was built with those flags set. It is not the repository default, so I did not rely on it.

**What runs concurrently**

- The library spawns no threads. The only thread-spawn sites the index finds are in `programs/`: `ssl_pthread_server.c:277` (`handle_ssl_connection`), `benchmark.c:430` (a Windows timer thread used for alarms), and two signal handlers (`benchmark.c:444` and `ssl_server2.c:1699`).
- `ssl_pthread_server.c:24` refuses to build unless both threading macros are set, so the one real multithreaded example is off in the default build.
- Signal handlers are asynchronous contexts, not threads. They are only a concern if they touch library state.

So by default, concurrency exists only if the application makes it: multiple threads calling into the library on shared contexts or on the PSA subsystem.

**What the mutexes protect when enabled** (from source reads, since the index's lock layer does not model these)

| Guard | Protects | Where |
|---|---|---|
| Per-context `ctx->mutex` | RNG state (CTR_DRBG, HMAC_DRBG), entropy sources, RSA context, SSL session cache, SSL ticket keys, SSL cookie secrets | `ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`, `rsa.c`, `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c` |
| `heap.mutex` | The static heap allocator | `memory_buffer_alloc.c:544-562` |
| `mbedtls_threading_key_slot_mutex` | The PSA key slot table | `psa_crypto.c:2022`, `psa_crypto_slot_management.c:199-1090` |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global init flags and state | `psa_crypto.c:141-165` |
| `mbedtls_threading_psa_rngdata_mutex` | The PSA RNG state | `psa_crypto.c:8030-8083`, `psa_crypto_random.c:147` |
| `mbedtls_threading_readdir_mutex` | `readdir` in X.509 directory loading | `x509_crt.c:1611` |
| `mbedtls_threading_gmtime_mutex` | Non-reentrant `gmtime`, only when the platform lacks `gmtime_r` | `platform_util.c:189` |

The per-context mutexes guard one object each. The PSA mutexes are global. Keys in the slot table are only safe to use while their slot's state is held, as `psa_crypto.c:1305-1320` shows.

**Caveats**

- The index's lock layer records one identity, `mutex->mutex` (library/threading.c:51-104), with low confidence, and no nested acquisitions. That is a flat view of the lock layer and does not prove deadlock freedom. The table above comes from source reads.
- `mbedtls_config.h` (around line 3740) says that any multithreaded use of PSA, or of TLS/X.509/PK functions with `MBEDTLS_USE_PSA_CRYPTO`, requires `MBEDTLS_THREADING_C`. Without it, a multithreaded application is on its own.

**To make a build thread-safe**, enable `MBEDTLS_THREADING_C` plus one backend (`MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`), and call `psa_crypto_init()` once before spawning threads.