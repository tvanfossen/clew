**Short answer:** in the default configuration, the library has no mutexes and creates no threads. The only concurrency is whatever threads the application starts and calls into the library from. The mutex code only exists when you turn on `MBEDTLS_THREADING_C`.

**Why the default build has no locks**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`). `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also commented out, and nothing in `include/`, `configs/` or `scripts/` defines them on by default.
- Every `mbedtls_mutex_*` call in `library/` sits inside `#if defined(MBEDTLS_THREADING_C)`, so with the default config those sections compile away.
- `library/` spawns no threads. The four spawn sites the index finds are all in `programs/`, and those are also gated off by default.

**What runs concurrently by default**

Only the application's threads. The library's own code is not synchronized, so a single context (an SSL session, a DRBG, an entropy context, the PSA key store) must not be used from two threads at once unless the application serializes access. I read this from the code and the gating; I did not check the project's thread-safety documentation.

The four spawn sites in the repo, all application or test code:

| Site | Kind | Gated by |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | per-connection pthread running `handle_ssl_connection` | `MBEDTLS_THREADING_C` and `_PTHREAD`, both off by default |
| `programs/test/benchmark.c:430` | Win32 `TimerProc` via `mbedtls_set_alarm` | platform |
| `programs/test/benchmark.c:444` | `sighandler` (alarm signal) | platform |
| `programs/ssl/ssl_server2.c:1699` | `term_handler` signal handler | platform |

The two signal handlers are asynchronous with respect to the main thread. Nothing in the library's logic protects them.

**What the mutexes protect when threading is enabled**

Per-object locks, each guarding its own context's state:
- `ssl_cache.c` (`cache->mutex`): session cache
- `ssl_ticket.c` (`ctx->mutex`): session ticket keys
- `ssl_cookie.c` (`ctx->mutex`): DTLS cookie state
- `entropy.c` (`ctx->mutex`): entropy pool
- `ctr_drbg.c` and `hmac_drbg.c` (`ctx->mutex`): DRBG state
- `rsa.c` (`ctx->mutex`): RSA context

Global locks, each guarding process-wide state:
- `memory_buffer_alloc.c` (`heap.mutex`): the single buffer-allocator heap. This also needs `MBEDTLS_MEMORY_BUFFER_ALLOC_C`, which is off by default.
- `mbedtls_threading_key_slot_mutex`: PSA key slots, used in `psa_crypto.c` and `psa_crypto_slot_management.c`.
- `mbedtls_threading_psa_globaldata_mutex`: PSA global data, used in `psa_crypto.c` and `psa_crypto_slot_management.c`.
- `mbedtls_threading_psa_rngdata_mutex`: the PSA RNG state, used in `psa_crypto.c` and `psa_crypto_random.c`.
- `mbedtls_threading_gmtime_mutex`: `gmtime` in `platform_util.c`, because `gmtime` returns a shared static buffer.
- `mbedtls_threading_readdir_mutex`: `readdir` in `x509_crt.c`.

The mutex type is `mbedtls_threading_mutex_t`, and the global ones are defined in `library/threading.c:188-189` with `MUTEX_INIT`, which expands to `{ PTHREAD_MUTEX_INITIALIZER, 1 }`.

**Caveats**

- The index's lock layer shows only one identity, `mutex->mutex` in `threading.c`, because it does not model struct-member locks. The call-site list above comes from a grep. That grep was capped at 250 lines, so it is representative, not exhaustive.
- The index found no nested lock holdings. That is a statement about this index's view, not a proof of deadlock freedom.
- Some lock calls ignore their return value. For example, `psa_crypto.c:130-131` and `psa_crypto.c:2022` call `mbedtls_mutex_lock` without checking it, while most other PSA sites use `PSA_THREADING_CHK_RET`. A failed lock there would go unnoticed.