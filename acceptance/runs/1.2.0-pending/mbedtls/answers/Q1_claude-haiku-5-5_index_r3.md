**Short answer:** with the shipped defaults, mbedtls runs no threads of its own and takes no locks. Concurrency is whatever the application does with the library, and the library protects nothing on its own.

**Why the defaults matter**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787`, and `MBEDTLS_THREADING_PTHREAD` is commented out at `:2196`. So `threading.c` compiles to nothing useful, and every lock site in the library sits behind `#if defined(MBEDTLS_THREADING_C)`.
- The index was built with both flags set by the operator (`configured_macros` in the search reply). Its lock and gate results therefore describe a threaded build, not the default. Don't quote them as default behaviour.

**What runs concurrently by default**

- **Library threads:** none. The index found four spawn sites, all in `programs/`: `ssl_pthread_server.c:277` (per-connection pthreads), `benchmark.c:430` and `:444` (timer thread and signal handler for `mbedtls_set_alarm`), and `ssl_server2.c:1699` (a `term_handler` signal handler). `library/` has none.
- **Signal dispositions (process-global, not thread-related):**
  - `library/net_sockets.c:112` calls `signal(SIGPIPE, SIG_IGN)` on the non-Windows, non-EFI path. This changes the whole process's SIGPIPE behaviour, and it is the only one of these I read the gate for.
  - `library/sha256.c:185-199` and `sha512.c:178-199` temporarily swap the SIGILL handler with `sigaction`, using `setjmp`/`longjmp`, to probe for crypto instructions. This is a process-wide side effect that is unsafe if another thread uses SIGILL at the same time. I did not confirm the gate that limits it to particular platforms.

**What protects what, if `MBEDTLS_THREADING_C` is enabled**

The mutex type is `mbedtls_threading_mutex_t`. Lock and unlock go through function-pointer variables (`threading.c:103`) that default to pthread implementations, and `MBEDTLS_THREADING_ALT` lets you substitute your own. Locking failures are returned as errors.

| Lock | Protects | Where |
|---|---|---|
| per-object `mutex` in `ssl_cache`, `ssl_ticket`, `ssl_cookie` | that context's state | e.g. `ssl_cache.c:84` |
| `ctx->mutex` in `entropy` | entropy sources and pool | `entropy.c:93`, `:179`, `:254`, `:294` |
| `ctx->mutex` in `ctr_drbg`, `hmac_drbg`, `rsa` | DRBG state, some RSA operations | `ctr_drbg.c:703`, `hmac_drbg.c:388`, `rsa.c:1239` |
| `heap.mutex` | the static buffer allocator | `memory_buffer_alloc.c:544`, `:558` |
| `mbedtls_threading_gmtime_mutex` | the `gmtime` wrapper | `platform_util.c:189` |
| `mbedtls_threading_readdir_mutex` | `readdir` during cert path parsing | `x509_crt.c:1611` |
| `mbedtls_threading_psa_globaldata_mutex` | global PSA state | `psa_crypto.c:141`, `psa_crypto_slot_management.c:200` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state | `psa_crypto.c:131`, `psa_crypto_random.c:147` |
| `mbedtls_threading_key_slot_mutex` | PSA key-slot table | `psa_crypto.c:2022` |

Note that the PSA globals are shared across every caller in the process, so they become a contention point under load.

**What the index can and cannot tell you**

- The lock layer reports one identity, `mutex->mutex`, with `identity_confidence: low`. It does not separate per-object locks, so it cannot show which lock protects which instance.
- It reports zero nested holdings. That is not a proof of deadlock freedom. I read the code paths for the psa and entropy locks directly and did not find nested acquisition there, but I did not audit every path.
- The library itself is not thread-safe per context. Two threads must not use the same SSL, cipher, or DRBG context at once, even with threading enabled, because the mutexes only cover the internal state listed above. I did not check the public docs for this, so treat it as the usual contract rather than a verified statement.