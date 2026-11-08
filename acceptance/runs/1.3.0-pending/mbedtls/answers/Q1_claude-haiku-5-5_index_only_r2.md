**Short answer:** with the default configuration the library runs no threads and takes no locks. The mutex and thread code only comes into play when the integrator enables `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD`, and then it protects shared library state.

**Default configuration**

- `MBEDTLS_THREADING_C` defaults to off (`include/mbedtls/mbedtls_config.h:3787`) and `MBEDTLS_THREADING_PTHREAD` defaults to off (`mbedtls_config.h:2196`).
- Everything in `library/threading.c` sits behind those gates. So do the mutexed heap wrappers in `memory_buffer_alloc.c` and the `mbedtls_mutex_lock` calls in `psa_unregister_read_under_mutex`.
- The index was built with both macros forced on, so the thread and lock listings below describe that variant. The shipped default is read from the header default, since no `config_header` is declared.

**What runs concurrently**

- **In the library:** no thread is created. The only spawn sites the index finds are in sample programs: `programs/ssl/ssl_pthread_server.c:277` (one pthread per client connection, running `handle_ssl_connection`), `programs/test/benchmark.c` (a signal handler and a Windows `TimerProc`), and `programs/ssl/ssl_server2.c` (`term_handler`). The library's concurrency is whatever threads the caller brings.
- **Caller-driven concurrency:** the library is reentrant only as far as the locks below cover. Any other shared object is the caller's problem.

**What the locks protect (when THREADING_C is on)**

| Object | Protects | Where |
|---|---|---|
| `heap.mutex` | the static heap in `memory_buffer_alloc.c`; calloc and free wrappers take it | `buffer_alloc_calloc_mutexed` (`:541`) |
| `mbedtls_threading_key_slot_mutex` | PSA key slot unregistration | `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global data | `threading.c:189` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state | `threading.c` |
| `mbedtls_threading_gmtime_mutex`, `..._readdir_mutex` | `gmtime` and `readdir` results, which are not reentrant | `threading.c` |

The `mbedtls_mutex_lock` calls into `threading_mutex_lock_pthread` also come from the entropy, CTR-DRBG, HMAC-DRBG, RSA, SSL cache, cookie and ticket, and X.509 code. I did not read each of those sites, so I can't say exactly which state each one guards.

**Caveats**

- The lock identity is weak. The one acquisition the index resolves is `mutex->mutex` with scope unknown and low confidence. Treat the named globals above as the objects, not the index's lock rows.
- The index found zero nested lock holdings. That is not a proof of deadlock freedom.
- I did not check lock-free or atomic paths. The index reports neither, so I can't say whether any exist.