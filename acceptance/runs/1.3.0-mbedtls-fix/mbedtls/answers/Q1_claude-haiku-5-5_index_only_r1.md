**Short answer:** in the default build, nothing in the library runs concurrently with anything, because the mutex layer is compiled out. The only threads in the repository are in sample programs. With threading enabled, the library takes locks at the entry points of its shared-state subsystems, and the shared objects are protected by their own per-object mutexes.

**Default configuration: no locking at all**

- `MBEDTLS_THREADING_C` (`include/mbedtls/mbedtls_config.h:3787`), `MBEDTLS_THREADING_PTHREAD` (`:2196`) and `MBEDTLS_THREADING_ALT` (`:2185`) all default to off.
- `library/threading.c` is gated on `MBEDTLS_THREADING_C`, so the pthread backend and the global mutex objects are absent from a default build.
- Every call site in the library is wrapped in `#if defined(MBEDTLS_THREADING_C)`. That includes the entropy, CTR-DRBG, HMAC-DRBG, PSA key-slot, PSA random, SSL cache, ticket, cookie and RSA init/free paths, and the buffer allocator and debug output.
- The library itself spawns no threads. The index's thread layer lists four spawn sites, all in `programs/`.

**Threads that exist (all in sample programs)**

| Thread | Where | Notes |
|---|---|---|
| `handle_ssl_connection` | `programs/ssl/ssl_pthread_server.c:277` (`thread_create`) | The only real concurrent user of the library. Its reach is about 1094 members. |
| `TimerProc` | `programs/test/benchmark.c:430` | Win32 alarm timer. |
| `sighandler` | `programs/test/benchmark.c:444` | Signal-handler context. |
| `term_handler` | `programs/ssl/ssl_server2.c:1699` | Signal-handler context. |

The index's `threads` layer shows no mutex use in the two signal handlers or the alarm timer. I did not open their bodies, so that is the index's view, not a source check.

**With `MBEDTLS_THREADING_C` plus the pthread backend enabled**

Locks are taken through global function pointers (`mbedtls_mutex_lock` at `library/threading.c:103`, initialised to `threading_mutex_lock_pthread`). The backend is therefore swappable through `MBEDTLS_THREADING_ALT`.

What each lock protects, from the index's caller and declaration data:

| Lock (`threading.c`) | Guards (verified or inferred) |
|---|---|
| `heap.mutex` (per heap, `memory_buffer_alloc.c:541`) | Verified: wraps `buffer_alloc_calloc` and free. |
| `mbedtls_threading_psa_globaldata_mutex` (`:189`) | Inferred from callers: PSA global state (`psa_get_initialized`, `psa_get_drivers_initialized`, `psa_start/finish_key_creation`, `psa_destroy_key`). |
| `mbedtls_threading_key_slot_mutex` (`:188`) | Inferred from callers: PSA key-slot table (`psa_get_and_lock_key_slot`, `psa_close_key`, `psa_purge_key`, `psa_unregister_read_under_mutex`). |
| `mbedtls_threading_psa_rngdata_mutex` (`:190`) | Inferred from callers: PSA RNG state (`psa_random_internal_generate`, `psa_random_reseed`, `psa_random_deplete`). |
| `mbedtls_threading_readdir_mutex` (`:182`) | Inferred from name only: the readdir path. |
| `mbedtls_threading_gmtime_mutex` (`:185`) | Inferred from name only: `gmtime` is not reentrant. |
| Per-object mutex inside each context | Inferred from callers: entropy, CTR-DRBG, HMAC-DRBG, SSL session cache, ticket keys, cookie secrets. |

The per-object locks are held inside `mbedtls_ctr_drbg_random`, `mbedtls_entropy_gather`, `mbedtls_hmac_drbg_random`, `mbedtls_ssl_cache_get/set/remove`, `mbedtls_ssl_ticket_parse/write`, `mbedtls_ssl_cookie_check/write` and `mbedtls_x509_crt_parse_path`, among others.

**Weak points I found in the source as indexed**

- `threading_mutex_init_pthread` (`threading.c:51–64`) ignores the return of `pthread_mutex_init`, and its own comment says using an uninitialised pthread mutex is undefined behaviour. The state check exists only in tests.
- `buffer_alloc_calloc_mutexed` (`memory_buffer_alloc.c:541–552`): if `mbedtls_mutex_unlock` fails, it returns NULL and drops `buf` without freeing it, so the allocation leaks.
- The index's lock layer shows one identity, `mutex->mutex`, with scope unknown and confidence low. Every acquisition goes through a function pointer, so the index cannot tie a lock to the object it protects. The mapping above comes from the callers of those pointers, not from the lock layer.