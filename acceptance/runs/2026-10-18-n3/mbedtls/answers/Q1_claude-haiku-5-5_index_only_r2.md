**Short answer:** with the default configuration, the library runs no concurrent code of its own, and none of its mutexes exist. The threading layer is compiled out, so the only concurrency comes from the example and test programs, which are not part of the library.

**Default state (from the index)**

- `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are both recorded as `default_state: off`. Everything in `library/threading.c` is gated by one or both, and each lock call site is inside an `#if MBEDTLS_THREADING_C` block.
- The index was built with both macros forced on by a flag, so it cannot tell you what the shipped config does. It has no `config_header` declared.
- For `PTHREAD`, the default site is `include/mbedtls/mbedtls_config.h:2196`. For `THREADING_C`, the cited default site is `configs/config-symmetric-only.h:73`, which is a variant config, not the shipped default. Treat "off" for `THREADING_C` as the index's inference and confirm it in `mbedtls_config.h`.

**What runs concurrently**

The index finds four thread or signal spawn sites, all outside `library/`:

| Spawn site | Kind | Role |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | pthread (`handle_ssl_connection`) | Example server, one thread per connection |
| `programs/test/benchmark.c:430` | Win32 timer (`TimerProc`) | Benchmark alarm |
| `programs/test/benchmark.c:444` | signal handler (`sighandler`) | Benchmark alarm |
| `programs/ssl/ssl_server2.c:1699` | signal handler (`term_handler`) | Server termination |

**What the locks protect when threading is enabled**

`mbedtls_mutex_*` are function pointers. With `PTHREAD` they point at `pthread_mutex_lock/unlock`. The protected objects are:

- `mbedtls_threading_key_slot_mutex` guards the PSA key-slot table. `psa_unregister_read_under_mutex` (`library/psa_crypto_slot_management.c:931`) takes it around `psa_unregister_read`. This is the one lock whose use the index shows in full.
- `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex` are declared for PSA global data and PSA RNG state. The index does not enumerate their users.
- `mbedtls_threading_readdir_mutex` and `mbedtls_threading_gmtime_mutex` are declared (the gmtime one is used only under `THREADING_USE_GMTIME`). The index does not enumerate their users.
- `heap.mutex` in `library/memory_buffer_alloc.c:68` (a static `buffer_alloc_ctx`) protects the heap. `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` (`:541-552`) wrap calloc and free in lock/unlock. This is the only lock whose full critical section is shown.
- The index also resolves lock-function callers in the DRBG, entropy, SSL cache/cookie/ticket, X.509 path parsing and PSA paths. Those are the call sites that would take the lock; the index does not show what each one protects.

**Caveats**

- There are no nested lock holdings. The index reports zero two-lock critical sections. That is a database result, not a deadlock-freedom proof.
- The one lock identity in the index is `mutex->mutex`, with low identity confidence. The per-object locks above are named by declaration, not by the index tracking each object.
- By default the DRBG, entropy, heap and PSA paths take no locks. Sharing one context across threads is unsafe unless the application serialises access itself.