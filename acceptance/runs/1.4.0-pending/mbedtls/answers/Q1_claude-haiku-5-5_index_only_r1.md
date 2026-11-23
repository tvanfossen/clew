**Short answer:** with mbedtls's shipped defaults, the library runs no concurrency at all. The mutex and thread code is compiled out. The only concurrent code that does run is in the test programs, which use signal handlers, not library threads.

**Why the library is single-threaded by default**

- `MBEDTLS_THREADING_C` is off by default (`include/mbedtls/mbedtls_config.h:3787`).
- `MBEDTLS_THREADING_PTHREAD` is off by default (`include/mbedtls/mbedtls_config.h:2196`).
- Every mutex call site is gated on `MBEDTLS_THREADING_C`, so with the defaults they compile to nothing. That includes the PSA key-slot lock in `psa_crypto_slot_management.c:931-947`, the heap lock in `memory_buffer_alloc.c:541-552`, and the DRBG, entropy, SSL cache, cookie and ticket locks.
- The index was built with both macros forced on (`configured_macros_source: flag`), so the lock and thread data below describes the threaded build, not the default one. I'm inferring the default from the `default_state` fields, not from reading the header.

**What runs concurrently in the threaded build**

The index finds 4 spawn sites, all in `programs/`, none in `library/`:

| Thread / handler | Where | Gated by threading? |
|---|---|---|
| `handle_ssl_connection` (pthread per client) | `programs/ssl/ssl_pthread_server.c:277` | Yes |
| `sighandler` (SIGALRM, timer) | `programs/test/benchmark.c:444` | No, only `HAVE_TIME` and `TIMING_ALT` |
| `TimerProc` (Win32 timer) | `programs/test/benchmark.c:430` | Windows only |
| `term_handler` (SIGTERM) | `programs/ssl/ssl_server2.c:1699` | No, only `!_WIN32` |

The library has no thread-spawning code of its own.

**What protects what (threaded build)**

- Each mutex is a global of type `mbedtls_threading_mutex_t`, initialised by `MUTEX_INIT` in `library/threading.c:182-190`.
- `mbedtls_threading_key_slot_mutex` is the only one whose use site I confirmed. It wraps `psa_unregister_read(slot)` in `psa_unregister_read_under_mutex`, which protects PSA key-slot state.
- `mbedtls_threading_psa_globaldata_mutex`, `mbedtls_threading_psa_rngdata_mutex`, `mbedtls_threading_gmtime_mutex` and `mbedtls_threading_readdir_mutex` are declared and initialised, but I did not confirm their use sites. Their purposes are only what their names suggest.
- The default lock implementation is pthread: `mbedtls_mutex_lock` is a function pointer initialised to `threading_mutex_lock_pthread` (`threading.c:103`). `mbedtls_threading_set_alt` can replace it, but only when `MBEDTLS_THREADING_ALT` is set, which is off by default.
- The lock layer finds one identity, `mutex->mutex`, at low confidence. It reports no nested two-lock holdings, which the tool calls a definitive empty result, not proof of deadlock-freedom.

**Caveat on the signal handlers**

`term_handler` sets a flag and calls `mbedtls_net_free` on the listen and client sockets from signal context. `sighandler` sets `mbedtls_timing_alarmed`. Neither takes a lock. These are test-program races, not library ones. The index does not model the interaction between handler and main-loop state.