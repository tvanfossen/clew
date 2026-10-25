**Short answer:** in the default configuration the library runs no threads and takes no locks. Any concurrency comes from the application that links it. The mutex code only becomes active when the application enables `MBEDTLS_THREADING_C`, and the index reports that option as off by default.

**What runs concurrently**

- **Library:** nothing. The index finds no thread spawns under `library/`.
- **Programs:** four spawn sites, all in `programs/`, none in the library:
  - `programs/ssl/ssl_pthread_server.c:277` spawns `handle_ssl_connection` per connection.
  - `programs/test/benchmark.c:430` and `:444` spawn an alarm timer thread and a signal handler (`TimerProc`, `sighandler`).
  - `programs/ssl/ssl_server2.c:1699` installs a `term_handler` signal handler.

**What protects what (only when `MBEDTLS_THREADING_C` is on)**

- **Lock primitive:** `mbedtls_mutex_lock` is a function pointer, initialised to `threading_mutex_lock_pthread` (`library/threading.c:103`). That function calls `pthread_mutex_lock(&mutex->mutex)` (`threading.c:75-86`). The pthread backend is additionally gated by `MBEDTLS_THREADING_PTHREAD`, and the index reports it as off by default.
- **Per-object mutexes:** the library's main use is the per-context mutex in `mbedtls_entropy_context`. `mbedtls_entropy_func` (`library/entropy.c:270`) locks `ctx->mutex` around the gather-and-extract step. The same lock-pointer pattern is reached from entropy add/gather/update, `ctr_drbg_random`, `hmac_drbg_random`, `rsa_public`/`rsa_private`, the SSL cache get/set/remove, the SSL cookie and ticket functions, `x509_crt_parse_path`, and the PSA key-slot and RNG paths.
- **Global mutexes** (`include/mbedtls/threading.h`, defined in `library/threading.c:182-190`):

| Mutex | Protects |
|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key-slot table |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global state |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state |
| `mbedtls_threading_gmtime_mutex` | `gmtime` (non-reentrant) |
| `mbedtls_threading_readdir_mutex` | `readdir` (non-reentrant) |

- **Allocator:** `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` lock around the stack-buffer allocator.

**Caveats**

- The index was built with both `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` passed as flags, so the analysis describes the threaded build. I did not verify the shipped default from the header. The index reports both macros as `default_state: off`, but it records no `config_header`, and I could not read `mbedtls_config.h`. Treat the default-off claim as the index's reading, not a confirmed line.
- The lock index holds one identity, `mutex->mutex` in `threading.c`. It does not resolve acquisitions made through the function pointers in the callers, so it cannot show which lock covers which shared state at each call site. The table above comes from the global variable declarations and the caller list, not from observed lock ordering.
- The lock layer shows no nested holdings, so there is no lock-ordering risk in what the index can see. That is not a proof of deadlock freedom.