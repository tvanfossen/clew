**Short answer:** with the library's default configuration, the library itself runs no threads and takes no locks. Concurrency comes only from the sample programs, and the mutexes are not compiled in.

**What is gated off by default**

- `MBEDTLS_THREADING_C` defaults to off (`include/mbedtls/mbedtls_config.h:3787`). Every mutex wrapper sits behind it, including the pthread implementation (`library/threading.c:18`, `:50`), which also needs `MBEDTLS_THREADING_PTHREAD`, default off at `mbedtls_config.h:2196`.
- The index was built with both macros set as build flags, so the `configured_macros` field shows them as on. That reflects the index build, not the shipped default. The default states above come from the header.

**What runs concurrently**

Only the four spawn sites the index found, all in `programs/`:

| Spawn site | Kind | Notes |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` (`handle_ssl_connection`) | pthread, one per client | Gated on `THREADING_C` and `THREADING_PTHREAD`, both default off. Only exists when those are enabled. |
| `programs/test/benchmark.c:444` (`sighandler`) | signal handler | Gated on `MBEDTLS_HAVE_TIME`, default on. Writes `mbedtls_timing_alarmed`. |
| `programs/test/benchmark.c:430` (`TimerProc`) | Win32 timer thread | Windows-only path. I did not check its gate. |
| `programs/ssl/ssl_server2.c:1699` (`term_handler`) | signal handler | Sets `received_sigterm` and frees the listen and client sockets. |

None of the spawn sites is in `library/`. The index only sees the spawn primitives its build searches for (pthread, signal, Win32 timer). A project's own RTOS or thread wrapper would not appear here.

**What protects what, when threading is enabled**

- **Five global mutexes** are declared in `include/mbedtls/threading.h` and defined in `library/threading.c:182-190`, all initialised with `MUTEX_INIT`:
  - `mbedtls_threading_key_slot_mutex` guards the PSA key-slot path. `psa_unregister_read_under_mutex` (`library/psa_crypto_slot_management.c:931`) takes it around `psa_unregister_read(slot)`. The index does not record the data accessed, so that is the only protected operation I can confirm.
  - `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex`: I found no consumers in the index. Their names suggest PSA global and RNG state, which I have not verified.
  - `mbedtls_threading_gmtime_mutex` and `mbedtls_threading_readdir_mutex`: likely serialise the non-reentrant `gmtime` and `readdir`, judging by the names only.
- **Heap mutex**: `heap.mutex` in `library/memory_buffer_alloc.c` wraps `buffer_alloc_calloc` and `buffer_alloc_free` (lines 541–563). `buffer_alloc_free_mutexed` returns without freeing if the lock fails, which the source comment justifies as preferring a leak over heap corruption.
- **Other lock users**: the DRBG, entropy, SSL cache, cookie, ticket, x509 path and RSA code all reach the mutex through the function-pointer wrappers (`threading_mutex_lock_pthread` and its unlock counterpart, which have many `fnptr` callers). I did not check which data each one guards.

**Caveats**

- The index has one lock identity, `mutex->mutex`, with scope unknown and low confidence. It cannot say which object each acquisition refers to.
- No critical section nests a second lock. The index treats this as a definitive empty result, not proof of deadlock freedom.
- `threading_mutex_init_pthread` (`threading.c:51`) notes that locking an uninitialised pthread mutex is undefined behaviour, and that state transitions are checked only in tests.