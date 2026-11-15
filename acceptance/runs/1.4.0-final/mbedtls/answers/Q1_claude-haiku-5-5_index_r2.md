**Short answer:** with the default configuration, mbedtls runs no concurrency of its own and has no mutexes. `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are both commented out in `include/mbedtls/mbedtls_config.h` (lines 3787 and 2196). Everything that locks is compiled out, so the library runs on whatever thread calls it and protects nothing.

**What runs concurrently by default**

- **Inside the library:** nothing. The index finds no thread spawn in `library/`. Its four spawn sites are all in `programs/`: the pthread SSL server (`ssl_pthread_server.c:277`), the benchmark alarm handlers (`benchmark.c:430, 444`), and the `ssl_server2` signal handler (`ssl_server2.c:1699`).
- **Your application:** whatever threads you create. The library runs on those threads and has no internal concurrency of its own.

**What protects what, when threading is enabled**

Threading is on only when you enable `MBEDTLS_THREADING_C` plus a backend (`MBEDTLS_THREADING_PTHREAD` or your own `MBEDTLS_THREADING_ALT`). Then the lock calls are compiled in:

| Lock | Protects |
|---|---|
| Per-object mutexes in `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c`, `entropy.c`, `hmac_drbg.c`, `rsa.c` | Shared state inside that context object, so one object can be used from several threads. |
| `mbedtls_threading_key_slot_mutex`, `mbedtls_threading_psa_globaldata_mutex`, `mbedtls_threading_psa_rngdata_mutex` (`psa_crypto*.c`) | PSA global state: the key-slot table, global data, and the RNG state. |
| `mbedtls_threading_readdir_mutex` (`x509_crt.c`) | The directory-reading path used when loading certificates from a directory. |
| `mbedtls_threading_gmtime_mutex` (`platform_util.c`) | `gmtime()` only on the `PLATFORM_UTIL_USE_GMTIME` path. Otherwise it calls `gmtime_r`, which needs no lock. |
| `heap.mutex` (`memory_buffer_alloc.c`) | The static heap allocator. |

Note that `ctr_drbg.c` has a gated mutex too, but I did not confirm its lock sites because the grep was truncated at 250 lines.

**What is unprotected by default**

Without threading, any object shared across threads is a data race. That includes an `mbedtls_entropy_context`, a DRBG, a session cache or ticket context, and the PSA global state. The PSA initialisation path (`mbedtls_psa_crypto_init` and its global data) is unguarded, so the usual pattern is to initialise once from one thread before starting others. The static heap allocator, if you use it, is also unguarded.

**Caveats**

- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` passed as flags, so its lock and thread rows describe a threaded build. Its `default_state: off` gate annotations confirm the shipped default, which is what the question asks about.
- The lock layer reports one identity, `mutex->mutex`, from `threading.c`. That is a spelling, not a count of mutex objects.
- The server example (`ssl_pthread_server.c`) gives each connection its own SSL context, so it is safe only because the threading layer is enabled; the default build does not compile it.