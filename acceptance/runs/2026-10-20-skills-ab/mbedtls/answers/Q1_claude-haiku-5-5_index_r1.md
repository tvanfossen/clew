**Short answer:** in the default configuration, the library runs no mutexes and no threads of its own. Every lock in the library is compiled out, and the only concurrency is in the sample programs, which are not part of the library.

**What is off by default**

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`). `library/threading.c` is wrapped entirely in `#if defined(MBEDTLS_THREADING_C)` (line 18), so the global mutexes do not exist in a default build.
- `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also off. There is no backend even if the layer were turned on.
- `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is off (line 3076), so the heap's `buffer_alloc_*_mutexed` wrappers are not built.

**What is on by default**

- `MBEDTLS_PSA_CRYPTO_C` is enabled (line 3334). PSA keeps its own process-wide state in `static psa_global_data_t global_data` (`library/psa_crypto.c:124`), and with the threading layer off, nothing protects it.
- The header's own documentation says that if more than one thread may call any PSA function, you must enable `MBEDTLS_THREADING_C` (`mbedtls_config.h:3749`). With the default build, the library is therefore only safe for single-threaded use, or for use where the application serialises all calls itself.

**What runs concurrently in the shipped programs**

| Thread or handler | Where | Gated by | Protection |
|---|---|---|---|
| `handle_ssl_connection` (one pthread per client) | `programs/ssl/ssl_pthread_server.c:98`, spawned at line 277 | `MBEDTLS_THREADING_C` + `_PTHREAD`, both off by default | Each thread owns its own `mbedtls_ssl_context`. The shared `mbedtls_ssl_config` is read-only after setup. The debug callback `my_mutexed_debug` serialises output through the program's own `debug_mutex` (line 65). |
| `sighandler` (SIGALRM) | `programs/test/benchmark.c:435` | Timing and platform gates | Sets `mbedtls_timing_alarmed = 1` and does nothing else. No lock. |
| `TimerProc` (Win32 timer thread) | `programs/test/benchmark.c:410` | Win32 only | Same flag write, no lock. |
| `term_handler` (SIGTERM) | `programs/ssl/ssl_server2.c:1070` | Non-Windows | Sets `received_sigterm` and closes the listen and client sockets to unblock accept/read. No lock. |

Note that `ssl_pthread_server.c` is a sample of what a multithreaded application can do. It is not a configuration the library enables for you.

**What each mutex protects, if you enable `MBEDTLS_THREADING_C`**

All of these are defined in `library/threading.c:182–190` and declared in `include/mbedtls/threading.h`.

- **`mbedtls_threading_psa_globaldata_mutex`** guards `global_data.initialized`, the driver-wrapper state, and most of the PSA context. It is taken in `psa_crypto.c` around `psa_crypto_init` and its helpers (lines 141, 159, 8407, 8439) and in `psa_crypto_slot_management.c:200`.
- **`mbedtls_threading_psa_rngdata_mutex`** guards the RNG state in `global_data.rng_state`. It is taken in `psa_get_initialized` (line 131), in `psa_crypto_random.c:147`, and around RNG seeding and querying in `psa_crypto.c:8030–8083` and `8384–8449`. The doc says `mbedtls_psa_random_free` is not thread-safe at all.
- **`mbedtls_threading_key_slot_mutex`** guards the key store. The doc says it protects every read or write of `slot->state` and `slot->registered_readers`, and every traversal of the store. `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) is the wrapper. About 20 call sites in `psa_crypto.c` and `psa_crypto_slot_management.c` take it.
- **`mbedtls_threading_gmtime_mutex`** serialises `gmtime()` in `library/platform_util.c:189–201`, but only when `MBEDTLS_HAVE_TIME_DATE` is set and `MBEDTLS_PLATFORM_GMTIME_R_ALT` is not. It is needed because `gmtime()` returns a pointer to static storage.
- **`mbedtls_threading_readdir_mutex`** serialises `readdir()` in `library/x509_crt.c:1611–1660`, used when loading a certificate directory.

Each of these is held for a short critical section. The PSA key-slot lock is the only one that nests across calls, and the doc does not describe a lock order between the PSA mutexes.

**Gaps in what I could verify**

- The index's lock layer returned only one identity, `mutex->mutex` in `threading.c` (`scope: unknown`). It does not model the `mbedtls_threading_*` globals, which I found by grep. Its `nestings` field is empty, which the index reports as "no two-lock holdings", not as proof of lock-order safety.
- I did not check whether `MBEDTLS_THREADING_ALT` or the PTHREAD backend is used by any default test configuration. I also did not check the `configs/` profiles beyond what the index reported for `MBEDTLS_THREADING_C`.