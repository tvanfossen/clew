**Short answer:** In a default build the library starts no threads and takes no locks of its own. Whatever concurrency exists comes from the application that links it, plus a few sample programs. The mutex layer exists, but it is compiled out unless threading is enabled, and the index cannot tell me which data each mutex guards.

**Which build the index describes.** The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` forced on by flag, so every threading and lock result below describes a threaded build. It records no config header, so it cannot confirm the shipped default. What it does show: `MBEDTLS_THREADING_PTHREAD` has default state off at `include/mbedtls/mbedtls_config.h:2196`, and `MBEDTLS_THREADING_C` has no definition site (it is commented out). Both suggest threading is off by default, which matches what I expect of mbedtls, but the index does not prove it.

**What runs concurrently (4 spawn sites, all in `programs/`, none in `library/`):**

| Context | Where | Under default config |
|---|---|---|
| `handle_ssl_connection` pthread, one per client | `programs/ssl/ssl_pthread_server.c:277` | Not compiled: gated by `MBEDTLS_THREADING_C` and `_PTHREAD`, both off |
| `term_handler` signal handler (SIGTERM) | `programs/ssl/ssl_server2.c:1699` | Runs. Its gate is only `_WIN32`, so it is live on POSIX builds |
| `sighandler` signal handler (benchmark alarm) | `programs/test/benchmark.c:444` | Benchmark only, behind timing-config gates |
| `TimerProc` via `_beginthread` | `programs/test/benchmark.c:430` | Windows benchmark only |

`term_handler` sets `received_sigterm` and closes `listen_fd` and `client_fd` from signal context. `sighandler` sets `mbedtls_timing_alarmed`. Both are asynchronous, and neither takes a lock.

**What protects what:**

- **The mutex abstraction** (`library/threading.c`, `include/mbedtls/threading.h`). Four function pointers, `mbedtls_mutex_init`, `_free`, `_lock` and `_unlock`, are initialised to the pthread implementations (`threading.c:101–104`). An application can replace them. The only lock acquisition the index records is inside `threading_mutex_lock_pthread` at `threading.c:81`, on `mutex->mutex`, exclusive. That is the pthread mutex inside the caller's `mbedtls_threading_mutex_t`.
- **Library state.** The index does not link any mutex to the data it guards. The lock's scope is "unknown" and its identity confidence is low. The library code gated on `MBEDTLS_THREADING_C` is the likely shared-state surface: `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c`, `memory_buffer_alloc.c`, `x509_crt.c`, and the `psa_crypto*` files. The index only shows those as gate sites. It does not show which mutex each one takes.
- **Sample server thread slots.** `thread_create` (`ssl_pthread_server.c:246`) joins finished slots and reuses the `threads[]` array, using a `thread_complete` flag as the handoff. The index shows no lock around that array.

**Why the lock list is misleading.** It contains one row. That reflects the index's blind spot, not the library's design. Every library call goes through `mbedtls_mutex_lock` as a function pointer, and the lock layer does not model calls through function pointers. The "no nesting" result is therefore weak evidence of deadlock-freedom.

**What I could not settle from the index:**

1. Whether `MBEDTLS_THREADING_C` is off in the shipped `mbedtls_config.h`. Declaring `preprocessor.config_header` would answer it.
2. Which library call sites actually take `mbedtls_mutex_lock`. Dossiering the callers of `mbedtls_mutex_lock` or the gated functions (e.g. `mbedtls_ctr_drbg_random`, `mbedtls_ssl_cache_get`) would show that.
3. Whether the `threads[]` handoff in the sample server is race-free. That needs reading the source, which the index tools don't give me.