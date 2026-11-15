**Short answer:** in a default build, the library creates no threads and takes no locks. Concurrency comes entirely from the application. The mutex code only activates when `MBEDTLS_THREADING_C` is enabled, and even then the locks protect shared library state, not the caller's data.

**Default configuration**

- `MBEDTLS_THREADING_C` defaults to off (`include/mbedtls/mbedtls_config.h:3787`). `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` also default to off.
- `library/threading.c` is wrapped entirely in `#if MBEDTLS_THREADING_C` (line 18). Every mutex call site in the library is gated on it, so by default none of them compile in.
- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set as flags, so the caller and lock facts below describe the threaded build. I could not confirm the shipped default from the index because no `config_header` is declared.

**Where threads come from (4 spawn sites, all in `programs/`, none in `library/`)**

| Thread / context | Where | What it does |
|---|---|---|
| `handle_ssl_connection` (pthread) | `programs/ssl/ssl_pthread_server.c:277` | One thread per client connection. Each owns its `mbedtls_ssl_context` and `client_fd`. It shares the `config` pointer from `thread_info`. |
| `sighandler` (ISR) | `programs/test/benchmark.c:444` | Signal handler that sets `mbedtls_timing_alarmed = 1`. |
| `TimerProc` (Win32) | `programs/test/benchmark.c:430` | Windows timer thread that sets the same flag. Gated on `_WIN32`. |
| `term_handler` (ISR) | `programs/ssl/ssl_server2.c:1699` | Signal handler in the SSL test server. |

The two alarm handlers only set a flag, with no locking. Neither the library nor its own sample programs contain a spawn site inside `library/`, so the library never creates its own threads.

**What the mutexes protect (threaded build)**

The lock type is `mbedtls_threading_mutex_t`, wrapping a `pthread_mutex_t`. Its lock path is `threading_mutex_lock_pthread` (`library/threading.c:75-86`).

1. **Global library mutexes** (`library/threading.c:182-190`, declared in `include/mbedtls/threading.h`):
   - `mbedtls_threading_key_slot_mutex`: PSA key slots. `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931-947`) wraps `psa_unregister_read` with it. Its callers include `psa_open_key`, `psa_close_key`, `psa_purge_key` and most `psa_*` operations that touch a slot.
   - `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex`: PSA global state and RNG state, initialised in `mbedtls_threading_set_alt`.
   - `mbedtls_threading_readdir_mutex` (only with `MBEDTLS_FS_IO`) and `mbedtls_threading_gmtime_mutex` (only with `THREADING_USE_GMTIME`), which protect `readdir` and `gmtime` for non-reentrant platforms.
2. **Memory buffer allocator:** `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` (`library/memory_buffer_alloc.c:541-552`) take `heap.mutex` around the allocator. These apply only when the buffer allocator is used.
3. **Per-object locks in shared-context code:** the lock primitive has callers across the DRBG and entropy code (`mbedtls_ctr_drbg_random`, `mbedtls_hmac_drbg_random`, `mbedtls_entropy_gather`, `mbedtls_entropy_func`), the SSL session cache (`mbedtls_ssl_cache_get/set/remove`), the cookie and ticket code (`mbedtls_ssl_cookie_*`, `mbedtls_ssl_ticket_*`), `mbedtls_rsa_public/private`, `mbedtls_x509_crt_parse_path`, and the PSA key-creation and RNG functions. These protect the shared context each function is called on. The index does not name the object each lock guards (one lock identity, `mutex->mutex`, scope unknown, confidence low), so this mapping is inferred from the callers rather than verified.

**Caveats**

- Spawn detection is pattern-based. A platform primitive outside the configured set would not appear, so the count is exact only for the patterns this build searched.
- `MBEDTLS_TEST_MUTEX_USAGE` (`programs/ssl/ssl_test_lib.c:448-470`) is a test-only switch, not a library setting.
- The index does not show whether a `mbedtls_ssl_config` shared across connection threads is read-only after setup. That would need a source read to confirm.