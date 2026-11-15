**Short answer:** with default settings, mbedtls runs no threads of its own and takes no locks. The mutex code is compiled out, so the library is single-threaded from its own point of view. Concurrency only appears if the integrator enables `MBEDTLS_THREADING_C` and runs the library from several threads.

**What is on by default**

- `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` both default to off (`include/mbedtls/mbedtls_config.h:3787` and `:2196`). `MBEDTLS_THREADING_ALT` also defaults to off (`:2185`).
- Every mutex call I checked sits behind `#if defined(MBEDTLS_THREADING_C)`. That covers `ssl_cache_get`, `entropy_func`, `psa_unregister_read_under_mutex`, and the `buffer_alloc_*_mutexed` wrappers in `memory_buffer_alloc.c`.
- The index's `configured_macros` lists THREADING_C and PTHREAD, but that comes from the operator's build flags, not the shipped default. I am relying on the default-state values above.

**What runs concurrently**

The index finds four thread or signal-handler spawn sites, all in `programs/`, none in `library/`:

| Entry | Where | What it is |
|---|---|---|
| `handle_ssl_connection` (pthread) | `programs/ssl/ssl_pthread_server.c:277` | Example server, one thread per connection (about 1,094 members) |
| `TimerProc` (Win32) | `programs/test/benchmark.c:430` | Timer thread for the benchmark alarm |
| `sighandler` (ISR) | `programs/test/benchmark.c:444` | Signal handler for the alarm |
| `term_handler` (ISR) | `programs/ssl/ssl_server2.c:1699` | Signal handler that sets a termination flag |

Only the pthread server is a real multi-threaded use of the library. Its `my_mutexed_debug` uses the same mutex abstraction.

**What the mutexes protect (with THREADING_C on)**

| Mutex | Protects | Where |
|---|---|---|
| `heap.mutex` | The `memory_buffer_alloc` heap (calloc/free) | `memory_buffer_alloc.c:541` |
| `ctx->mutex` in entropy | The entropy accumulator and sources | `entropy.c` (`entropy_func` at ~`:270`) |
| `cache->mutex` | The SSL session cache, around find, load and store | `ssl_cache.c:74` |
| `mbedtls_threading_key_slot_mutex` | PSA key slots, around `psa_unregister_read` | `psa_crypto_slot_management.c:931` |
| `mbedtls_threading_psa_globaldata_mutex`, `psa_rngdata_mutex` | PSA global and RNG state | `threading.c:189–190` (I did not trace their callers) |
| `mbedtls_threading_readdir_mutex` | `readdir`, which is not thread-safe | `threading.c:182`, only with `MBEDTLS_FS_IO` |
| `mbedtls_threading_gmtime_mutex` | `gmtime`, which is not thread-safe | `threading.c:185`, only with `THREADING_USE_GMTIME` |

The mutex is initialized by `mbedtls_threading_set_alt`. The key-slot, globaldata and rngdata mutexes are set up only when `MBEDTLS_PSA_CRYPTO_C` is on, which it is by default.

**Limits of this answer**

- The lock layer shows a single lock identity, `mutex->mutex`, with low confidence. It does not separate the per-object mutexes above. The mapping here comes from the per-function dossiers, not the lock layer.
- The layer reports no nested two-lock holdings. That does not prove deadlock-freedom.
- The index has no config header for this target, so the shipped default comes from the `default_state` values on the gate sites, not from a direct read of the header.