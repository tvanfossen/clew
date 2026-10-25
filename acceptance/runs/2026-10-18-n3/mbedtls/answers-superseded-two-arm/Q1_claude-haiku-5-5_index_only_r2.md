**Short answer:** Under the default configuration the library runs no internal concurrency and protects nothing. The index can't confirm that default, though. The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set by the operator, and it has no config header for the repo, so the shipped default is unknown from here. What it does show is that no indexed header has a definition site for `MBEDTLS_THREADING_C`, which usually means it's commented out. The index says nothing about the default for `MBEDTLS_THREADING_PTHREAD` either. From general knowledge, mbedtls ships with threading off, but that is outside the index.

**With threading enabled (the build the index used):**

*What runs concurrently*

- **The library starts no threads.** Its concurrency is whatever the caller creates. The index's thread layer found 4 spawn sites, all in `programs/`, none in `library/`.
- **`programs/ssl/ssl_pthread_server.c`**: `handle_ssl_connection` runs one pthread per accepted connection (spawned via `thread_create`, gated on both threading macros). Each thread has its own `mbedtls_ssl_context` and client fd, but they all read the same `thread_info->config`. Whether concurrent use of a shared `ssl_config` is safe is not something the index shows.
- **Signal handlers (kind `isr`)**: `term_handler` in `ssl_server2.c` sets `received_sigterm` and calls `mbedtls_net_free` on `listen_fd` and `client_fd` from signal context, racing the main loop (my reading, not an index claim). `sighandler` in `benchmark.c` sets `mbedtls_timing_alarmed`. `TimerProc` (Win32 only) sets the same flag from a timer thread.

*What the mutexes protect*

| Object | Where used | What the index shows |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | `psa_get_and_lock_key_slot` | Held across the whole lookup, including loading a persistent key, so another thread can't load and destroy the same key in between. Unlocked on every return path. Gated on `MBEDTLS_THREADING_C` inside `MBEDTLS_PSA_CRYPTO_C`. |
| `heap.mutex` | `buffer_alloc_calloc_mutexed` / `_free_mutexed` (`memory_buffer_alloc.c`) | Serializes the stack allocator's calloc/free. |
| `readdir_mutex` | Initialized in `mbedtls_threading_set_alt`, gated on `MBEDTLS_FS_IO` | Presumably guards `readdir`. No acquisition site found. |
| `gmtime_mutex` | Initialized in `set_alt`, gated on `THREADING_USE_GMTIME` | `mbedtls_platform_gmtime_r` calls lock/unlock, but the index doesn't show which mutex. |
| `psa_globaldata_mutex`, `psa_rngdata_mutex` | Initialized in `set_alt` under `MBEDTLS_PSA_CRYPTO_C` | Names suggest PSA global and RNG state. No acquisition sites found in the index. |
| Per-context locks (entropy, DRBGs, SSL cache/cookie/ticket, RSA, X.509 path parsing) | Entropy gather/poll and CTR/HMAC-DRBG random call lock/unlock through the function pointers | The index shows the call edges but not which context field is locked. |

*How the locking works*

- `mbedtls_mutex_init/lock/unlock/free` are function pointers defaulting to `threading_mutex_*_pthread`, which wrap `pthread_mutex_*`.
- `mbedtls_threading_set_alt` swaps in a custom implementation and initializes the four global mutexes. It is gated on `MBEDTLS_THREADING_ALT`, whose origin is undeclared.
- The init function notes that locking an uninitialized pthread mutex is undefined behaviour and is only checked in tests.

**Gaps in what I can tell you**

- The shipped default config is not in the index. Declaring `preprocessor.config_header` would settle it.
- The lock layer has one identity, `mutex->mutex`, scope unknown, confidence low. It can't map locks to objects. Its "no two-lock holdings" result means none were detected, not that deadlock is impossible.
- Thread detection is pattern-based. A project's own spawn helper or an RTOS wrapper would be invisible unless `thread_patterns` is declared.