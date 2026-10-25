**Short answer:** in the default configuration, the library runs no threads and takes no locks. The mutex code is compiled out. The only concurrency is in the sample and test programs, and those are either async signal handlers or code that won't build without the threading layer.

**What the default config does**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, so it is off. `MBEDTLS_THREADING_ALT` and `MBEDTLS_THREADING_PTHREAD` are also off (lines 2185, 2196).
- Every `#if defined(MBEDTLS_THREADING_C)` block in `library/` is therefore excluded. That covers the per-context mutexes in entropy, DRBGs, RSA, SSL ticket/cookie/cache, and the PSA globals.
- The header's own documentation says the library assumes a non-threaded environment unless this option is enabled (lines 3744–3747).

**What actually runs concurrently (default build)**

| Where | What | Kind |
|---|---|---|
| `programs/ssl/ssl_server2.c:1699` | `term_handler` | signal handler (async) |
| `programs/test/benchmark.c:444` | `sighandler` via `mbedtls_set_alarm` | signal handler (async) |
| `programs/test/benchmark.c:430` | `TimerProc` | Windows timer thread |
| `programs/ssl/ssl_pthread_server.c:277` | `handle_ssl_connection` | one pthread per connection |

The pthread server can't run by default. Lines 24–27 of that file fail the build with "MBEDTLS_THREADING_PTHREAD not defined" unless the threading options are enabled.

The index's thread layer agrees on these four spawn sites, all in `programs/`. The library itself spawns nothing.

**What protects what, when you enable `MBEDTLS_THREADING_C`**

- **Global mutexes**, declared in `library/threading.c:182–190`:
  - `readdir_mutex` (with `MBEDTLS_FS_IO`) guards `readdir()` in `x509_crt.c:1610–1660`.
  - `gmtime_mutex` guards `gmtime_r` emulation in `platform_util.c:188–204`. It exists only when the platform lacks a thread-safe `gmtime_r`.
  - `key_slot_mutex`, `psa_globaldata_mutex` and `psa_rngdata_mutex` (with PSA) guard PSA's implicit shared state. The key slot table and global data are in `psa_crypto_slot_management.c` and `psa_crypto.c`. The RNG data mutex covers the PSA RNG state in `psa_crypto_random.c` and `psa_crypto.c`.
- **Per-object mutexes**, each in `ctx->mutex`, lock and unlock around the context's mutable state:
  - `entropy.c`
  - `ctr_drbg.c`, `hmac_drbg.c`
  - `rsa.c`
  - `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`
  - `memory_buffer_alloc.c`, which guards the single heap through `heap.mutex`

  I checked these against the lock and unlock call sites. I did not read each guarded region in full, so the exact scope of each lock is inferred from its placement.

**Backends**

- With `MBEDTLS_THREADING_PTHREAD`, the mutexes are real `pthread_mutex_t` values, statically initialised.
- With `MBEDTLS_THREADING_ALT`, the function pointers start as "fail" stubs. `mbedtls_threading_set_alt()` must be called before any lock is used, or every lock returns an error.

**Gaps and caveats**

- The index sees only one lock identity, `mutex->mutex` in `threading.c`, with low confidence. The per-object locks are member expressions, which the index does not model. The "0 nestings" result means only that the index found no nested holdings. It does not prove the code is deadlock-free.
- The header says that with THREADING_C off, a multithreaded application is unprotected if any thread uses PSA (lines 3749–3751). It also says TLS 1.3 connections need the threading layer regardless of configuration (line 3761). So under the default config, sharing a PSA-backed or TLS 1.3 context across threads is undefined behaviour in this build. The library does not enforce that.