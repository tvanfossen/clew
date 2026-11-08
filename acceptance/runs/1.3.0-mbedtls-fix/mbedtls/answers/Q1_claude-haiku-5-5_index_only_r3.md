**Short answer:** by default, the mbedtls library starts no threads and takes no locks. Its only concurrency is what the embedding application adds, and the mutexes exist only when the threading layer is enabled. Caveat: the index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` forced on, and it has no config header, so the shipped default comes only from the `default_state: off` entries it reports (`mbedtls_config.h:2196` and `:3787`). Confirm those lines before relying on this.

**What runs concurrently**

| Source | Where | When it exists |
|---|---|---|
| Library code | `library/` | Never spawns threads. All four spawn sites the index found are in `programs/`. |
| Per-connection pthread | `programs/ssl/ssl_pthread_server.c` (`thread_create` → `handle_ssl_connection`) | Only when the threading macros are on (file gate at line 30). Example program, not library. |
| Windows timer thread | `programs/test/benchmark.c` (`mbedtls_set_alarm` → `TimerProc`) | Windows-only, test benchmark. |
| Signal handlers | `sighandler` (`benchmark.c`), `term_handler` (`ssl_server2.c`) | Asynchronous, not threads. The index labels them `isr`. |

So with defaults, concurrency is entirely the application's. The library's own job is to be re-entrant across separate `mbedtls_*_context` objects and to take its shared-state locks when the threading layer is compiled in.

**What the mutexes protect (pthread backend)**

- `threading.c` provides function pointers `mbedtls_mutex_init/free/lock/unlock`, defaulting to the pthread implementations. `mbedtls_threading_set_alt` (also gated off by default) swaps them out.
- File-scope mutexes, initialised in `mbedtls_threading_set_alt`:
  - `mbedtls_threading_readdir_mutex` (with `MBEDTLS_FS_IO`)
  - `mbedtls_threading_gmtime_mutex` (with `THREADING_USE_GMTIME`)
  - PSA: `key_slot_mutex`, `psa_globaldata_mutex`, `psa_rngdata_mutex`
- Going by the names and the call graph, these guard readdir, gmtime's shared buffer, the PSA key-slot table, PSA global state, and PSA RNG state.
- Through the lock function pointer, the index shows these callers: the memory buffer allocator (`buffer_alloc_calloc/free_mutexed`), the entropy and CTR/HMAC-DRBG RNG paths, the SSL session cache, ticket and cookie code, RSA, many PSA key-slot and random functions, `x509_crt_parse_path`, and `platform_gmtime_r`.

**Limits of that mapping**

- The lock layer reports one lock identity, `mutex->mutex`, scope unknown, confidence low. It cannot tell the five global mutexes apart or say which one a given caller holds. Treat the protection mapping as "this call path is under a mutex", not "this mutex guards this object".
- Zero nested critical sections were found. That is an index result, not a proof of deadlock freedom.
- `threading_mutex_init_pthread` notes that locking an uninitialised pthread mutex is undefined behaviour and is not checked at runtime.

**Unprotected shared state (example server)**

- `threads[]` is shared between the main thread and workers. The worker sets `thread_info->thread_complete = 1` (`ssl_pthread_server.c:241`). The main thread reads `threads[i].data.thread_complete == 1` (`:258`) and then joins, memsets and reuses the slot. The index shows no lock here, and the flag is a plain `int`, so the cross-thread read has no synchronisation.
- `term_handler` runs asynchronously in `ssl_server2.c` and calls `mbedtls_net_free` on `listen_fd` and `client_fd`, which the main loop is using. No lock is involved. Whether this is safe depends on signal-safety and volatile semantics, which the index cannot settle.

These examples are test and demo programs, not the library, but they are the only places in the index where two real execution contexts touch shared state without a lock.