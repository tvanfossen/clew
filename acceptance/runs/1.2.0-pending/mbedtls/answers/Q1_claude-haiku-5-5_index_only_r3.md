**Short answer:** in the default configuration, mbedtls runs no threads of its own and takes no locks. Everything that uses a mutex sits behind `MBEDTLS_THREADING_C`, which is off by default. The only threads and signal handlers the index finds are in `programs/`, not `library/`.

**Default configuration**

- `MBEDTLS_THREADING_C` has default state `off`, declared at `include/mbedtls/mbedtls_config.h:3787`. Its `threading.c` gate (line 18) and the `psa_crypto_slot_management.c` and `memory_buffer_alloc.c` gates all depend on it.
- `MBEDTLS_THREADING_PTHREAD` is also `off` by default (`mbedtls_config.h:2196`).
- With both off, `library/threading.c` compiles to nothing, so the `mbedtls_mutex_*` function pointers, the global mutexes and the `pthread_mutex_*` calls are all absent.
- The index's `configured_macros` lists both macros as set, but that came from the operator's build flags, not from the repo's shipped config. The index holds no `config_header` for this target, so treat the default as the `mbedtls_config.h` value above.

**What runs concurrently**

- **In the library:** nothing spawns a thread. The thread layer's only library-side lock is the wrapper `threading_mutex_lock_pthread` (`library/threading.c:75`), which is not reached under the default config.
- **In the sample programs** (all gated by `MBEDTLS_THREADING_C`/`PTHREAD`, so not built by default):
  - `handle_ssl_connection` in `programs/ssl/ssl_pthread_server.c:277`, one pthread per accepted client, each with its own `mbedtls_ssl_context`.
  - `sighandler` in `programs/test/benchmark.c:444` and `term_handler` in `programs/ssl/ssl_server2.c:1699`, which are signal handlers.
  - `TimerProc` in `programs/test/benchmark.c:430`, a Win32 timer thread.
- The index counts 4 spawn sites, all first-party. Its spawn patterns cover only the primitives it knows, so a platform-specific spawn would not appear.

**What the mutexes protect, when threading is enabled**

| Object | Where declared | Protects (verified) |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | `threading.c:188` | PSA key slots; taken in `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) |
| `buffer_alloc` `heap.mutex` | `memory_buffer_alloc.c` | Heap; `buffer_alloc_calloc_mutexed` / `_free_mutexed` (lines 541+) wrap calloc and free |
| `mbedtls_threading_psa_globaldata_mutex` | `threading.c:189` | PSA global data (declared; users not checked) |
| `mbedtls_threading_psa_rngdata_mutex` | `threading.c:190` | PSA RNG data (declared; users not checked) |
| `mbedtls_threading_gmtime_mutex` | `threading.c:185` | `gmtime` (declared; users not checked) |
| `mbedtls_threading_readdir_mutex` | `threading.c:182` | `readdir` (declared; users not checked) |

The mutexes are `PTHREAD_MUTEX_INITIALIZER` wrappers (`MUTEX_INIT`). The entropy, CTR-DRBG and HMAC-DRBG code takes the same lock wrapper through `mbedtls_mutex_lock` (the dossier lists those callers), and the PSA crypto, SSL cache, cookie and ticket code do too. None of these were individually checked for which data the lock covers. The mutex layer shows no nested locking: there are zero two-lock critical sections.

**Implication:** under the default config, the library is not thread-safe in any sense the index can verify. If you call it from several threads, you must serialise access yourself or build with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD`. Even then, the index shows only the listed globals and the heap mutex. Whether every shared object is covered is unverified, because the lock layer resolves only one identity (`mutex->mutex`, low confidence).