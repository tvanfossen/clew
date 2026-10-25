**Short answer:** in a default build, mbedtls runs no concurrent code of its own, and it takes no locks. The mutex and thread code only exists when `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are enabled. Threads come from the sample programs, not the library.

**Caveat on the index.** This index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set by flag, so everything about locks below describes that threaded build. The index has no config header for this target, so it cannot confirm the shipped default. The gate rows show `MBEDTLS_THREADING_PTHREAD` defaulting to off at `include/mbedtls/mbedtls_config.h:2196`. For `MBEDTLS_THREADING_C`, the only default it reports is off in `configs/config-symmetric-only.h:73`, which is a preset, not the shipped header. From my knowledge of mbedtls, `MBEDTLS_THREADING_C` is commented out in `mbedtls_config.h`, but the index does not show that, so check the header before relying on it.

**What runs concurrently (threaded build)**

The library spawns no threads. Concurrency comes from the caller's threads entering the library. The index finds four spawn sites, all in `programs/`:

| Spawn site | Mechanism | What runs |
|---|---|---|
| `ssl_pthread_server.c:277` (`thread_create`) | `pthread_create` | One thread per client connection, running `handle_ssl_connection`. Finished slots are reclaimed with `pthread_join`. |
| `benchmark.c:430` (`mbedtls_set_alarm`) | `_beginthread` (Windows) | A `TimerProc` thread that sets an alarm flag. |
| `benchmark.c:444` | signal handler `sighandler` | Async context, not a thread. |
| `ssl_server2.c:1699` | signal handler `term_handler` | Async context, not a thread. |

Coverage is limited to the spawn primitives the index's patterns match, so other platform thread APIs would not appear.

**What the locks protect (threaded build)**

- **Five global mutexes**, all declared in `include/mbedtls/threading.h` and defined in `library/threading.c:182–190`: readdir, gmtime, PSA global data, PSA key slots, and PSA RNG data.
- **Lock primitive:** the mutex wraps a `pthread_mutex`. `threading_mutex_lock_pthread` (`threading.c:75–86`) returns `MBEDTLS_ERR_THREADING_BAD_INPUT_DATA` on NULL and `MBEDTLS_ERR_THREADING_MUTEX_ERROR` if the lock call fails.
- **Callers:** the lock and unlock functions are reached through function pointers, and the index resolves these edges. Callers that take the lock include:
  - entropy: `mbedtls_entropy_gather`, `add_source`, `func`, `update_manual`
  - DRBG: `mbedtls_ctr_drbg_random`, `mbedtls_hmac_drbg_random`
  - RSA: `mbedtls_rsa_private`, `mbedtls_rsa_public`
  - session cache, cookies and tickets: `mbedtls_ssl_cache_*`, `mbedtls_ssl_cookie_*`, `mbedtls_ssl_ticket_*`
  - X.509: `mbedtls_x509_crt_parse_path`
  - time: `mbedtls_platform_gmtime_r`, which wraps the non-reentrant `gmtime` path
  - PSA: key-slot and key-management functions, including `psa_get_and_lock_key_slot`
  - buffer allocator: `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed`

**Limits of what the index can say**

- **Which global guards which caller is not established.** The lock layer shows one identity, `mutex->mutex`, with scope unknown. Because the calls go through function pointers, the index cannot tell which of the five globals each caller takes. The mapping above is by name plus the caller list, not verified.
- **No nested locking.** The index reports zero two-lock holdings. That is not a proof of deadlock freedom.
- **Unguarded shared state is unknown.** The index does not say whether other library globals are shared without a lock.
- **Per-connection state in the sample server.** Each `handle_ssl_connection` thread has its own SSL context and client socket. The config it uses comes from a shared `base_info` copy. I did not verify whether that config is read-only across threads.