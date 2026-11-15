**Short answer:** by default, nothing inside the library runs concurrently and no mutex is taken. The mutex code is compiled out. What runs concurrently is whatever your application does with the library, and the only threads the index sees are in demo programs.

**Default configuration (as the index reads the shipped headers)**

- `MBEDTLS_THREADING_C` defaults off (`include/mbedtls/mbedtls_config.h:3787`). `library/threading.c` is wholly gated on it (lines 18–193), so every lock site in the library is `#if`'d out.
- `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` also default off (`mbedtls_config.h:2196`, `:2185`).
- The index was built with both THREADING flags set on the command line, so these defaults come from the header gate definitions, not from a declared config header. Treat "off" as the header's stated default, not a build I ran.

**What spawns threads (4 sites, all in `programs/`)**

| Thread entry | Site | Notes |
|---|---|---|
| `handle_ssl_connection` (pthread) | `programs/ssl/ssl_pthread_server.c:277` | One thread per accepted connection; the only one that reaches library code in the index |
| `sighandler` (ISR) | `programs/test/benchmark.c:444` | Alarm signal handler |
| `TimerProc` (Win32) | `programs/test/benchmark.c:430` | Windows timer callback |
| `term_handler` (ISR) | `programs/ssl/ssl_server2.c:1699` | Termination signal handler |

None of these are in `library/`. The library itself spawns nothing.

**What the mutexes protect when threading is enabled**

- **PSA key slot table**, `mbedtls_threading_key_slot_mutex` (`threading.c:188`). Taken in `psa_get_and_lock_key_slot` (`psa_crypto_slot_management.c:804`) and `psa_unregister_read_under_mutex` (`:931`). The lock is held across loading a persistent key so another thread cannot load and destroy it in between (comment at `:820`).
- **PSA global data** and **PSA RNG data**, `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex` (`threading.c:189–190`). They are initialised in `mbedtls_threading_set_alt`, but the index returned no lock sites for them, so I cannot name what they guard.
- **Readdir**, `mbedtls_threading_readdir_mutex` (`threading.c:182`, built only with `MBEDTLS_FS_IO`).
- **gmtime**, `mbedtls_threading_gmtime_mutex` (`threading.c:185`). `mbedtls_platform_gmtime_r` (`platform_util.c:173`) locks around `gmtime()`, which returns shared static storage, and only when the non-reentrant path is in use.
- **Per-object locks.** `mbedtls_entropy_gather` locks `ctx->mutex` (`entropy.c:249`). The buffer allocator locks `heap.mutex` in `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` (`memory_buffer_alloc.c:541`). The index also lists DRBG, RSA, SSL cache, cookie and ticket code as callers of the lock wrapper, but a caller list is not a list of lock sites, so I have not confirmed which of their state is guarded.

**Caveats**

- Every lock goes through one identity, `mutex->mutex` (`threading.c:81`), with scope unknown and low confidence. Individual globals are not distinguished in the lock layer.
- The index shows no two-lock nesting. That is not a proof of deadlock freedom.
- `threading_mutex_init_pthread` (`threading.c:51`) notes that locking an uninitialised pthread mutex is undefined behaviour. The library does not check this at runtime; it relies on tests.
- I found no lock protecting per-connection SSL context state. In the demo server each connection has its own thread, so connections do not share SSL contexts. An application that shares a context across threads gets no protection from the library.