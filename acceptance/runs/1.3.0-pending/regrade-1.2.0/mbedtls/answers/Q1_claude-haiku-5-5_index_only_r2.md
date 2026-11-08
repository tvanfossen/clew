**Short answer:** in the default configuration, the library runs no concurrent code and takes no locks. Every mutex in the tree sits behind `MBEDTLS_THREADING_C`, which ships off. Concurrency only appears in the bundled `programs/`, and the library's own locks only matter if the integrator enables threading.

**Default build (`MBEDTLS_THREADING_C` off, `mbedtls_config.h:3787`)**
- `library/threading.c` is compiled out (its gate spans lines 18–193), and so is every lock site that depends on `MBEDTLS_THREADING_C`. That covers the entropy, DRBG, RSA, SSL cache/cookie/ticket, PSA, and memory-buffer call sites.
- `MBEDTLS_THREADING_ALT` is also off by default (`mbedtls_config.h:2185`), so no platform mutex is installed either.
- Any sharing of contexts between threads is therefore the integrator's responsibility. The index shows no library-side lock protecting them.

**Threads that exist (4, all outside `library/`)**
- `handle_ssl_connection`, a pthread spawned in `programs/ssl/ssl_pthread_server.c:277`. That file is gated on `MBEDTLS_THREADING_C` (lines 24–492), so it is not built by default.
- `TimerProc` (Win32 timer) and `sighandler` (ISR), both from `mbedtls_set_alarm` in `programs/test/benchmark.c`.
- `term_handler`, a signal handler in `programs/ssl/ssl_server2.c:1699`.

**What the locks protect when threading is enabled**

| Lock | Guards (from its name and the sites that touch it) |
|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key-slot unregistration. `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) takes it around `psa_unregister_read`. |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global data. Declared and initialised; the index shows no use sites. |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG data. Declared and initialised; the index shows no use sites. |
| `mbedtls_threading_readdir_mutex` | `readdir` (only with `MBEDTLS_FS_IO`). Declared and initialised; no use sites shown. |
| `mbedtls_threading_gmtime_mutex` | `gmtime` (only with `THREADING_USE_GMTIME`). Declared and initialised; no use sites shown. |
| `heap.mutex` in `memory_buffer_alloc.c` | Serialises `buffer_alloc_calloc`/`free` via the `_mutexed` wrappers (lines 541–552). |
| Per-object mutexes | Initialised in the init functions of entropy, CTR-DRBG, HMAC-DRBG, RSA, SSL cache, cookie and ticket. Their use sites are not expanded here. |

**How the locks are wired**
- `mbedtls_threading_set_alt` (`threading.c:133`) installs the four function pointers (`mbedtls_mutex_init/free/lock/unlock`). It then initialises the global mutexes (readdir, gmtime, and the three PSA ones). The pointers are plain globals with no synchronisation, so this must run before any thread starts.
- The default pthread backend, `threading_mutex_init_pthread` (`threading.c:51`), calls `pthread_mutex_init`. Its comment notes that locking an uninitialised pthread mutex is undefined behaviour and is checked only in tests.
- Lock nesting: the index reports zero two-lock holdings. That is not a proof of deadlock freedom.

**Caveats on this answer**
- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` forced on by flag, and no `config_header` is recorded. The "off by default" claim comes from the default-state citations on the gating macro, not from reading the shipped config. Confirm against `include/mbedtls/mbedtls_config.h`.
- The lock inventory shows one identity, `mutex->mutex` in `threading.c`. It is a member expression, so the index cannot resolve which object each acquisition targets.
- The index does not show what the PSA global and RNG mutexes guard beyond their names, or whether PSA global state is safe without them.