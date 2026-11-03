**Short answer:** with the default `mbedtls_config.h`, the library runs no threads and takes no mutexes. Everything in `threading.c` is compiled out. Concurrency comes only from the application, and the thread spawns the index finds are in the sample programs under `programs/`.

**Default configuration**

- `MBEDTLS_THREADING_C` defaults to off (`include/mbedtls/mbedtls_config.h:3787`). Its gate covers all of `library/threading.c` (lines 18–193), so the mutex primitives and their function-pointer table don't exist.
- `MBEDTLS_THREADING_PTHREAD` also defaults to off (`mbedtls_config.h:2196`).
- Every lock site in the library sits behind `#if defined(MBEDTLS_THREADING_C)`. That includes the PSA key-slot paths in `psa_crypto_slot_management.c`, the allocator wrappers in `memory_buffer_alloc.c` (lines 540–564), and the gmtime path in `platform_util.c`. In a default build these are plain calls.
- The index was built with both macros set by flag, so `configured_macros` shows a non-default variant. The "off" defaults come from the header's `default_site`, not from that build.

**Threads the index finds (all in programs, none in the library)**

| Spawn site | Kind | Gated by |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` → `handle_ssl_connection` | pthread | `MBEDTLS_THREADING_PTHREAD` (off) |
| `programs/test/benchmark.c:430` → `TimerProc` | Win32 timer | test program |
| `programs/test/benchmark.c:444` → `sighandler` | signal handler | test program |
| `programs/ssl/ssl_server2.c:1699` → `term_handler` | signal handler | sample program |

Attribution is by spawn site with pattern matching, at medium confidence. Any spawn primitive the patterns don't know is invisible here. So the library has zero threads of its own, and the sample servers are the only places a second thread appears. Concurrency beyond that is whatever the embedding application adds.

**When threading is enabled: what each mutex protects**

| Mutex | Used by | What it guards |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | `psa_get_and_lock_key_slot` (held across the load-from-storage path), `psa_unregister_read_under_mutex` | The PSA key-slot table. The comment in `psa_get_and_lock_key_slot` says it must be held so another thread can't load and destroy a key between the "loaded?" check and marking the slot full. |
| `mbedtls_threading_psa_globaldata_mutex` | none resolved | Declared only. The name suggests PSA global state, but the index has no use sites. |
| `mbedtls_threading_psa_rngdata_mutex` | none resolved | Declared only. Name suggests PSA RNG state; unverified. |
| `mbedtls_threading_readdir_mutex` | none resolved | Declared only. Probably serializes `readdir`; unverified. |
| `mbedtls_threading_gmtime_mutex` | `mbedtls_platform_gmtime_r` | Only on the `PLATFORM_UTIL_USE_GMTIME` branch, which serializes `gmtime()`. On the default `gmtime_r` path it isn't taken. |
| `heap.mutex` (memory buffer allocator) | `buffer_alloc_calloc_mutexed`, `buffer_alloc_free_mutexed` | Serializes `calloc`/`free` over the single static heap. Free ignores lock failure and leaks rather than corrupt the heap. |

The index shows the callers that reach the pthread wrapper through the function-pointer table: entropy, CTR-DRBG, HMAC-DRBG, RSA, the SSL cache, cookie and ticket code, and X.509 path parsing. It does not resolve which mutex each of those call sites takes. The lock layer records one identity, `mutex->mutex` in `threading.c`, with scope unknown and zero nested holdings. So the table above is from names, call edges and the function-pointer graph, not from resolved lock identities.

**Caveats**

- The index doesn't record `mbedtls_threading_set_pthread`, so how the pthread implementation gets installed isn't verified.
- The PSA global-data, RNG-data and readdir mutexes have no use sites in the index. Their protected state is unverified.
- Zero nested lock holdings is a definitive result for this index, not a proof of deadlock-freedom.