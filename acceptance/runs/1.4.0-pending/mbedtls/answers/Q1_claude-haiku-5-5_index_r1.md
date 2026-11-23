**Short answer:** with the shipped defaults, mbedtls creates no threads and takes no mutexes. The library runs with whatever concurrency its caller gives it, and the mutex layer is compiled out.

**Why the layer is off by default**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787`. `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also off.
- Every mutex use in the library sits behind `#if defined(MBEDTLS_THREADING_C)`. That includes `ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`, `debug.c`, `error.c`, `platform_util.c` and `psa_crypto.c`. The index confirms this for `buffer_alloc_calloc_mutexed` in `memory_buffer_alloc.c:540`, whose gate is `default_state: off`.
- `library/` has no `pthread_create` anywhere. The only pthread hits are the mutex wrapper in `threading.c` and a version string in `version_features.c`.

**What runs concurrently by default**

| Who | Concurrency |
|---|---|
| Library (`library/`) | None of its own. Each call runs on the caller's thread. |
| Caller's threads | Whatever the application creates. Mbed TLS does not synchronise them. |
| `programs/` | Only when those programs are built. See below. |

The index found four spawn sites, all in `programs/`:

- `programs/ssl/ssl_pthread_server.c:277`: one `handle_ssl_connection` thread per client. This program needs `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` (guard at line 24).
- `programs/test/benchmark.c:430,444`: a timer thread (`TimerProc`) and a signal handler (`sighandler`), both from `mbedtls_set_alarm`.
- `programs/ssl/ssl_server2.c:1699`: a `term_handler` signal handler.

**What protects what, when the mutex layer is on**

The mutex layer is defined in `library/threading.c:188-199`. The shared state it protects is:

- `mbedtls_threading_key_slot_mutex`: the PSA key-slot table.
- `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex`: PSA global state and the RNG state. `psa_crypto.c:130` takes the RNG mutex in `psa_get_initialized`.
- `mbedtls_threading_gmtime_mutex`: serialises `gmtime` when it is not reentrant.
- `mbedtls_threading_readdir_mutex`: serialises `readdir`, compiled only with `MBEDTLS_FS_IO`.
- `heap.mutex` in `memory_buffer_alloc.c`: the optional buffer allocator, which wraps `calloc`/`free` in `buffer_alloc_*_mutexed`.
- Per-context locks in the DRBG and entropy code.

**What is unprotected by default**

Because `MBEDTLS_THREADING_C` is off while `MBEDTLS_PSA_CRYPTO_C` (line 3334) is on, the PSA global state, the key-slot table and the RNG state are guarded by nothing by default. This is my inference from the `#if` gates, not something I traced through `psa_crypto_init`. The consequence is that concurrent PSA initialisation or key use from two threads has no library-side protection in the default build.

The same applies to the DRBG and entropy contexts: concurrent use of one context from two threads is unsafe with the defaults. That is the usual Mbed TLS contract: a context is not thread-safe, and distinct contexts are fine.

**Limits of this answer**

The index's lock layer returned one lock identity (`mutex->mutex` in `threading.c`) and no nested holdings. It does not model the global mutex objects individually, so I relied on grepping the `#if` gates for the protection map. I did not read the bodies of the PSA or DRBG paths to confirm each unguarded access, so treat the "unprotected by default" list as the gate-level picture.