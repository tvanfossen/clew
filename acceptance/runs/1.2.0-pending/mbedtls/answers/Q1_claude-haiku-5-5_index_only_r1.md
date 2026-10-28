**Short answer:** with the default configuration, the library runs no threads of its own and takes no mutexes. Concurrency only exists if the integrator enables `MBEDTLS_THREADING_C`, and even then the library itself does not spawn threads. The only threads in this repository are in the example programs.

**Default configuration**

- `MBEDTLS_THREADING_C` is declared with default `off` at `include/mbedtls/mbedtls_config.h:3787`, and `MBEDTLS_THREADING_PTHREAD` is default `off` at `:2196`.
- Every mutex use I could find sits behind `MBEDTLS_THREADING_C`. That includes the allocator's `buffer_alloc_*_mutexed` wrappers (`library/memory_buffer_alloc.c:540`) and the whole of `library/threading.c` (gated 18–193).
- The index was built with both macros stated as flags, so the gate data shows them as on. That is the build I queried, not the shipped default. The index has no `config_header`, so it cannot confirm the default beyond the `mbedtls_config.h` declarations above.

**What runs concurrently (when threading is enabled)**

| Party | Concurrency | Source |
|---|---|---|
| Application threads calling the library | Yes. Each thread can call into mbedtls at once, and the library must be safe for that. | Caller's responsibility |
| Library-internal threads | None. The index finds no spawn site in `library/`. | 4 spawn sites, all in `programs/` |
| `handle_ssl_connection` (pthread) | One thread per accepted connection, each with its own `ssl` context. | `programs/ssl/ssl_pthread_server.c:277`, gated on `PTHREAD` |
| `term_handler` (signal) | Asynchronous. Sets `received_sigterm` and frees the listen and client sockets while the main loop may be using them. | `programs/ssl/ssl_server2.c:1699`, `_WIN32`-gated |
| `TimerProc` / `sighandler` (benchmark) | Windows timer thread, and a POSIX alarm handler, in the benchmark tool only. | `programs/test/benchmark.c:430, 444` |

The library's own code has no thread spawns, so the examples are the only real concurrency.

**What protects what (lock layer)**

- Lock wrapper: `mbedtls_threading_mutex_t` with `mbedtls_mutex_init/lock/unlock/free` in `include/mbedtls/threading.h`, backed by pthread functions in `library/threading.c`. The index finds one lock identity, `mutex->mutex` in `threading.c`, and that is only the wrapper's own internal use.
- Global mutexes, each declared in `threading.h` and defined with `MUTEX_INIT` in `threading.c`:
  - `mbedtls_threading_readdir_mutex` (line 182)
  - `mbedtls_threading_gmtime_mutex` (185)
  - `mbedtls_threading_key_slot_mutex` (188)
  - `mbedtls_threading_psa_globaldata_mutex` (189)
  - `mbedtls_threading_psa_rngdata_mutex` (190)
- `heap.mutex` in `memory_buffer_alloc.c` guards the static buffer allocator. Its calloc/free paths take the lock around the real allocation.

From the names, the key-slot mutex likely guards PSA key-slot state (`psa_unregister_read_under_mutex` in `psa_crypto_slot_management.h` suggests this), and the RNG-data mutex likely guards PSA RNG state. However, the index records no reader or writer sites for these globals, so I cannot confirm what each one actually protects. The `heap.mutex` coverage is confirmed from the source.

**Gaps and caveats**

- The index shows no nested locking. Its `nestings` field is empty, which is a definitive result for this index. It is not a proof of deadlock-freedom.
- The thread and lock counts are exact for this build's patterns only. A custom spawn primitive would not appear.
- The `mutex->mutex` lock identity has `identity_confidence: low`, so it is weak evidence about which object is locked.