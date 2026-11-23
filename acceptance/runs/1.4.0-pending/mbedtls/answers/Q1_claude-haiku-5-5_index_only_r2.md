**Short answer:** in the default configuration, the library runs no concurrency of its own and takes no locks. Every mutex in `library/` is compiled out, so any thread safety is the integrator's job. The concurrent code the index finds is in `programs/`, not in the library.

**Default build (what the index can establish)**

- `MBEDTLS_THREADING_C` is off by default (`include/mbedtls/mbedtls_config.h:3787`), and so is its backend, `MBEDTLS_THREADING_PTHREAD` (`:2196`). `MBEDTLS_THREADING_ALT` is also off (`:2185`).
- With `MBEDTLS_THREADING_C` off, the guarded code is absent. That includes `threading.c` (the pthread lock/unlock wrappers), the `heap.mutex` wrappers in `memory_buffer_alloc.c`, and `psa_unregister_read_under_mutex`.
- `MBEDTLS_PSA_CRYPTO_C` is on by default (`mbedtls_config.h:3334`). So PSA runs without its key-slot and global-data locks. The index shows no lock protecting PSA by default, and I read that as "the library does not protect it." I have not confirmed this against the shipped header itself.

**Thread creation found in the repo (4 spawn sites, all in `programs/`)**

| Spawn site | Kind | What it means |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | pthread, `handle_ssl_connection` | The only real multi-threaded consumer of the library. Its reachable set is about 1,094 members, so it calls into the library heavily. |
| `programs/test/benchmark.c:430` | win32 `TimerProc` | Timer for `mbedtls_set_alarm`. |
| `programs/test/benchmark.c:444` | ISR `sighandler` | Signal handler for the same alarm. |
| `programs/ssl/ssl_server2.c:1699` | ISR `term_handler` | Signal handler for termination. |

**What the library's locks would protect when enabled**

The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set as flags, so the lock data below describes that variant, not the default. The lock layer collapses everything into one identity, `mutex->mutex` (low confidence), so per-object locks are not separately resolved. The protection assignments below come from the global mutex declarations and their call sites:

| Lock | Protects (from call sites) |
|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key slot table: `psa_unregister_read_under_mutex`, used by `psa_open_key` and most `psa_*` entry points |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global state (declared; no dossier call site listed) |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state (declared; `psa_random_internal_generate` takes the mutex in `psa_crypto_random.c`) |
| `mbedtls_threading_readdir_mutex` | `readdir` (declared; not individually checked) |
| `mbedtls_threading_gmtime_mutex` | `gmtime` (declared; `mbedtls_platform_gmtime_r` takes the lock) |
| `heap.mutex` in `memory_buffer_alloc.c` | The static buffer allocator's `calloc`/`free` |
| Per-context mutexes | Entropy (`entropy.c`), CTR-DRBG, HMAC-DRBG, SSL session cache, SSL cookie, SSL ticket, and RSA. These are taken on their own context's mutex, not a global. |

**Other facts**

- The index finds no nested two-lock holdings. The tool itself says this is not proof of deadlock freedom.
- The thread/lock layers only reflect the configured variant, so the statements about the default come from the `default_state` gate data, not from a build with the default header. Confirming against `mbedtls_config.h` would take one read of that header.