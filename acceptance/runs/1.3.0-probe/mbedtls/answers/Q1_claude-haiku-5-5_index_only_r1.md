**Short answer:** with the shipped defaults, mbedtls's own library code runs no concurrency and takes no locks. The mutex and thread code only exists when the operator enables `MBEDTLS_THREADING_C`, which defaults to off. The only threads in the repository are in `programs/` (sample and test programs), not in the library.

**Default build (`MBEDTLS_THREADING_C` off)**

- `library/threading.c` is compiled out entirely (`threading.c:18-193` is gated on `MBEDTLS_THREADING_C`, default off at `include/mbedtls/mbedtls_config.h:3787`).
- Every mutex global is absent: `mbedtls_threading_key_slot_mutex`, `_psa_globaldata_mutex`, `_psa_rngdata_mutex`, `_gmtime_mutex`, `_readdir_mutex`.
- The heap lock in `memory_buffer_alloc.c` (`buffer_alloc_calloc_mutexed` / `_free_mutexed`, lines 540-564) is also gated on `MBEDTLS_THREADING_C`, so the allocator is unlocked.
- The PSA key-slot lock wrapper `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931-947`) is gated on `MBEDTLS_THREADING_C`. PSA Crypto itself is on by default, but its slot access is unlocked.
- The entropy, CTR-DRBG, HMAC-DRBG, SSL cache, ticket, cookie and X.509 path loaders all take these same locks only when `MBEDTLS_THREADING_C` is set (their gates are listed in the index).
- The library starts no threads. The thread list has no entries under `library/`.

So the only concurrency the default library faces is whatever the embedding application brings. The repository's own PSA thread-safety document says PSA API calls "are not thread-safe" in current releases (`docs/architecture/psa-thread-safety/psa-thread-safety.md`, "Thread-safety of the PSA subsystem"). Nothing in the library protects shared state across threads by default.

**What runs concurrently in this repository (all under `programs/`, none in the library)**

| Thread / handler | Where | Primitive | Gate |
|---|---|---|---|
| `handle_ssl_connection` | `programs/ssl/ssl_pthread_server.c:277` | pthread per connection | Needs `MBEDTLS_THREADING_PTHREAD` |
| `sighandler` | `programs/test/benchmark.c:444` | SIGALRM handler | Not a thread, an async signal |
| `TimerProc` | `programs/test/benchmark.c:430` | Win32 timer callback | Windows only |
| `term_handler` | `programs/ssl/ssl_server2.c:1699` | signal handler | Not a thread |

The pthread server is the only real concurrent workload. It uses `my_mutexed_debug` (`ssl_pthread_server.c`) as its debug callback and `debug_mutex` for log serialization, so it sets its own locking up from the program side rather than relying on the library.

**When `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are enabled**

- The pthread backend (`threading.c:50-111`) wraps `pthread_mutex_lock` / `unlock`. `threading_mutex_lock_pthread` (`threading.c:75-86`) is the only lock path the index resolves, via the `mbedtls_mutex_lock` function pointer.
- The globals are:
  - `mbedtls_threading_key_slot_mutex`: serializes PSA key-slot read registration.
  - `mbedtls_threading_psa_globaldata_mutex`: PSA global state.
  - `mbedtls_threading_psa_rngdata_mutex`: PSA RNG state.
  - `mbedtls_threading_gmtime_mutex`: `gmtime` (not reentrant).
  - `mbedtls_threading_readdir_mutex`: `readdir` (not reentrant).
- The heap, entropy, DRBG, SSL session cache, ticket and cookie code take `mutex` around their shared state when this is on.
- The index's lock layer shows one lock identity (`mutex->mutex` in `threading.c:81`) and no nested acquisitions. It records one spelling, not one object per context, so it cannot say which context each lock guards.

**Caveats**

- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` stated as operator flags, so the "gates" lists above describe that build. The off-by-default status comes from the header's `default_state` annotation. The index has no `config_header` for this target, so I cannot confirm the default from the repository's own config beyond those annotations.
- Thread detection is by spawn-site pattern at medium confidence. A spawn through a primitive outside its pattern set would not appear.
- "Nothing else protects anything" is the index's reading of the gated code, not a proof of freedom from races.