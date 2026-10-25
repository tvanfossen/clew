**Short answer:** in a default build, mbedtls runs nothing concurrently and has no internal locks. The mutex and thread code is compiled out. Any concurrency is the application's own threads calling into the library, and the library provides no protection for that.

**Caveat on the index:** it was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set as flags, so the threads and lock below come from that non-default build. The index has no config header for this target, so the repo's own default is not recorded. The default-off evidence is indirect:

- `MBEDTLS_THREADING_PTHREAD` has default state off at `include/mbedtls/mbedtls_config.h:2196`.
- `MBEDTLS_THREADING_C` has no definition site in `mbedtls_config.h`, which fits a commented-out `//#define`.

**What runs concurrently when threading is enabled (not the default)**

The index finds 4 spawn sites, all in `programs/`, not `library/`:

| Thread | Kind | Where | What it is |
|---|---|---|---|
| `handle_ssl_connection` | pthread | `programs/ssl/ssl_pthread_server.c:277` | One thread per client TLS session, created by `thread_create` |
| `sighandler` | signal handler | `programs/test/benchmark.c:444` | Sets `mbedtls_timing_alarmed` |
| `TimerProc` | Win32 thread | `programs/test/benchmark.c:430` | Sleeps, then sets the same alarm flag |
| `term_handler` | signal handler | `programs/ssl/ssl_server2.c:1699` | Sets `received_sigterm`, frees the listen and client sockets |

The library itself spawns nothing.

**What protects what (when enabled)**

- The only lock identity is `mutex->mutex`, taken in `threading_mutex_lock_pthread` (`library/threading.c:81`). The index gives it scope "unknown" and low confidence, so it cannot say which object each instance guards.
- The mutex calls are reached through function pointers (`mbedtls_mutex_lock`, `mbedtls_mutex_init`, `mbedtls_mutex_unlock`, defaulting to the pthread implementations at `threading.c:101–104`). The index resolves these callers:
  - **Allocator:** `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed`, guarding the heap.
  - **Entropy and DRBG:** `mbedtls_entropy_*` and `mbedtls_ctr_drbg_random` / `mbedtls_hmac_drbg_random`.
  - **PSA key slots:** `psa_get_and_lock_key_slot`, `psa_start/finish/fail_key_creation`, `psa_purge_key`, `psa_destroy_key`, `psa_close_key`, and the `psa_get_*_initialized` checks.
  - **PSA random:** `psa_random_reseed`, `psa_random_internal_generate`, `psa_random_deplete`, and related functions.
  - **SSL state:** `mbedtls_ssl_cache_get/set/remove`, `mbedtls_ssl_cookie_write/check`, `mbedtls_ssl_ticket_write/parse`.
  - **Other:** `mbedtls_rsa_public/private`, `mbedtls_x509_crt_parse_path`, `mbedtls_platform_gmtime_r`.
- The index found no nested lock holdings, so it records no lock-ordering dependency. It does not prove deadlock-freedom.
- Every one of these call sites is gated by `MBEDTLS_THREADING_C`, so none of them is compiled into a default build.

**Net for a default build:** no internal threads, no internal mutexes, and no state guarded by the library. A caller that shares an mbedtls context, PSA key slot, or DRBG across threads has to add its own synchronisation. The signal handlers in the test programs touch only plain flags, and the index shows no protection for them.