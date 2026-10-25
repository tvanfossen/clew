**Short answer:** In the default configuration, mbedtls creates no threads and takes no locks. The mutex code is compiled out. The only concurrency is whatever threads your application runs against the library. When threading is enabled, the mutexes protect a handful of library globals and the static heap, and the ones I could confirm are the GMT-conversion, PSA key-slot, and heap mutexes.

**What runs concurrently**

- The four thread spawn sites in the index are all in `programs/`, not `library/`: `handle_ssl_connection` (`ssl_pthread_server.c:277`, one pthread per client), `TimerProc` (`benchmark.c:430`, a Win32 alarm thread), and two signal handlers (`sighandler` in `benchmark.c:444`, `term_handler` in `ssl_server2.c:1699`). None of these is part of the library.
- The mutex code is gated by `MBEDTLS_THREADING_C`, whose default state is off. `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` also default to off. The index holds no definition site for the first two, so the "off" comes from the `default_site` lines in `mbedtls_config.h`. Those lines should be checked by hand.
- The index was built with `THREADING_C` and `PTHREAD` set by the operator, so the protection details below describe that build, not the shipped default.

**What is protected when threading is on**

| Protected item | Lock | Where |
|---|---|---|
| Static heap (`heap`) | `heap.mutex` | `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` in `memory_buffer_alloc.c`, gated by `THREADING_C` |
| PSA key-slot table | `mbedtls_threading_key_slot_mutex` | `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) wraps `psa_unregister_read` |
| GMT conversion (`gmtime` is not reentrant) | `mbedtls_threading_gmtime_mutex` | Initialized under `THREADING_USE_GMTIME`; `mbedtls_platform_gmtime_r` reaches the lock through the function pointer |
| `readdir` | `mbedtls_threading_readdir_mutex` | Initialized under `MBEDTLS_FS_IO`; I did not confirm its users |
| PSA global data and RNG data | `mbedtls_threading_psa_globaldata_mutex`, `mbedtls_threading_psa_rngdata_mutex` | Initialized under `MBEDTLS_PSA_CRYPTO_C`; I did not confirm their users |

The mutex is reached through the `mbedtls_mutex_lock` function pointer. The index lists these as callers of the pthread lock: entropy, CTR-DRBG and HMAC-DRBG random, SSL cache, cookie and ticket, RSA private and public, `x509_crt_parse_path`, and many PSA functions.

**How the lock layer is implemented**

- `mbedtls_threading_set_alt` (`threading.c:133`) replaces the four function pointers and initializes the global mutexes. The pthread implementation is the default when `THREADING_PTHREAD` is on.
- Each mutex is a `mbedtls_threading_mutex_t`, which wraps a `pthread_mutex_t`.
- The lock layer finds only one identity, `mutex->mutex`, with confidence "low", acquired inside `threading_mutex_lock_pthread`. Acquisitions made through the pointer are invisible to it, and it found zero nested holdings. That is not proof of deadlock freedom.

**Caveats**

- The index cannot show whether the library is safe to call from several threads at once. The mutexes cover only the globals and heap listed above. Other shared state, such as SSL contexts, is the application's responsibility.
- Items marked "I did not confirm" would need a source read to verify.