**Short answer:** in the default configuration the library creates no threads and takes no locks, so nothing inside mbedtls runs concurrently. Any concurrency comes from the application calling the library from several threads. The mutexes only exist when the build enables `MBEDTLS_THREADING_C`, and then they protect a small set of shared globals plus the heap.

**What runs concurrently**

- **Library code:** none. The index holds four spawn sites, all in `programs/` (`ssl_pthread_server.c`, `benchmark.c` ×2, `ssl_server2.c`). None are in `library/`. Two of the four are signal or timer handlers (`sighandler`, `term_handler`, `TimerProc`), which are asynchronous but also outside the library. This count covers only the thread primitives the index's patterns match.
- **Application threads:** whatever the integrator runs. The per-connection `handle_ssl_connection` thread in the example server is the model case: each thread has its own `ssl` context, and the shared `mbedtls_ssl_config` is read by all of them.

**Default build (what the index can say)**

- `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are both recorded as `default_state: off`. `MBEDTLS_THREADING_ALT` is also off. The `THREADING_C` default site cited is `configs/config-symmetric-only.h`, not the shipped header, but the shipped `mbedtls_config.h` has no live `#define` for it, so it is off there too.
- With these off, `threading.c` compiles to nothing, the heap wrappers are not built (`buffer_alloc_*_mutexed` is gated on `THREADING_C`, default off), and the lock call sites in the ctr_drbg, entropy, ssl_cache, ssl_cookie and ssl_ticket code are not compiled either.
- So in the default build, shared state (PSA key slots, the RNG and entropy contexts, the ssl session cache, the heap) is **unprotected**. Concurrent use is safe only if the application serializes calls.

**When threading is enabled (the index's build)**

- **Global mutexes**, all declared in `library/threading.c` and initialized with `MUTEX_INIT`:

  | Mutex | Protects (basis) |
  |---|---|
  | `mbedtls_threading_key_slot_mutex` | PSA key slot unregistration. Verified: `psa_unregister_read_under_mutex` wraps `psa_unregister_read` in lock/unlock. |
  | `mbedtls_threading_psa_globaldata_mutex` | PSA global state. Inferred from the name only. |
  | `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state. Inferred from the name only. |
  | `mbedtls_threading_gmtime_mutex` | `gmtime` static result. Inferred from the name only. |
  | `mbedtls_threading_readdir_mutex` | `readdir` directory stream. Inferred from the name only. |

- **Heap:** `heap.mutex` in `library/memory_buffer_alloc.c`. Verified: `buffer_alloc_calloc_mutexed` locks `heap.mutex` around `buffer_alloc_calloc`, and the free path does the same.
- **Pluggable:** `mbedtls_threading_set_alt` installs the four function pointers (`mbedtls_mutex_init/free/lock/unlock`) and initializes the global mutexes. The default lock function is `threading_mutex_lock_pthread`, which calls `pthread_mutex_lock` on the mutex's `->mutex` field.
- **Lock ordering:** the index records one lock identity (`mutex->mutex`, scope unknown) and zero nested acquisitions. That means no critical section calls into a second lock, which is not a proof of deadlock freedom.

**Gaps and caveats**

- The index was built with `THREADING_C` and `PTHREAD` forced on, so the lock and thread rows describe that variant. The index has no config header, so it cannot state what the repository's own default enables.
- Only the key-slot and heap critical sections were read in source. The other mutex-to-data mappings above are inferred from names, and I could not confirm which context structures take which lock.
- Concurrency in the default build is an application responsibility. The index cannot show how the application serializes its calls.