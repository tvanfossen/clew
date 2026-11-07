**Short answer:** in the default configuration, the library runs no concurrency at all. The mutexes and threads only exist when `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are enabled, and both default to off. The threads the index finds are in example programs that are gated by the same macros.

**What runs concurrently by default**

- **Library code:** nothing. The index finds no threads spawned from `library/`. Every `threading.c` function and every `mbedtls_threading_*` mutex is gated by `MBEDTLS_THREADING_C` (default off, `include/mbedtls/mbedtls_config.h:3787`). The pthread backend is gated by `MBEDTLS_THREADING_PTHREAD` (default off, `mbedtls_config.h:2196`).
- **Example programs:** `programs/ssl/ssl_pthread_server.c` spawns one pthread per connection (`handle_ssl_connection`, spawn at line 277). That code is also gated by the threading macros, so it compiles out by default.
- **Signal and timer handlers:** these are asynchronous with the main thread even without threading. `term_handler` in `programs/ssl/ssl_server2.c` sets `received_sigterm` and calls `mbedtls_net_free` on the listen and client fds. `sighandler` and `TimerProc` in `programs/test/benchmark.c` are the alarm path. The index shows no lock protecting the state these handlers touch. I did not check whether the benchmark alarm sites are themselves gated.

**What protects what, when threading is enabled**

The index's lock layer only sees one identity (`mutex->mutex` inside `threading_mutex_lock_pthread`), so the table below comes from dossier call sites, not from the lock layer.

| Lock | Protects (per index) |
|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key-slot reference counts. `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) wraps `psa_unregister_read`. Its callers include most `psa_*` operations. |
| `heap.mutex` (in `memory_buffer_alloc.c`) | The buffer allocator heap. `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` wrap the unlocked calloc and free. |
| `mbedtls_threading_psa_rngdata_mutex`, `mbedtls_threading_psa_globaldata_mutex` | Declared and initialised. I did not find their consumers. |
| `mbedtls_threading_readdir_mutex`, `mbedtls_threading_gmtime_mutex` | Declared and initialised. I did not find their consumers. |

Every lock goes through the function pointer `mbedtls_mutex_lock`, which defaults to `threading_mutex_lock_pthread` (`library/threading.c:103`). Callers reached through that pointer include the CTR-DRBG, HMAC-DRBG and entropy functions, the SSL cache, cookie and ticket code, `rsa_public` and `rsa_private`, `x509_crt_parse_path`, and `platform_gmtime_r`. The index attributes these by function-pointer edges, so treat the list as indirect.

**Limits of this answer**

- The index was built with the threading macros passed as flags, and no config header is recorded for the target. The "off by default" result comes from the default sites in `mbedtls_config.h`, not from a configured header. Whether another config file in the repo enables threading is not confirmed here.
- Spawn detection is `medium` confidence and covers only the primitives the index knows about.