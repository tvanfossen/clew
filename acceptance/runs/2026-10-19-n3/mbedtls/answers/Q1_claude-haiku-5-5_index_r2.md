**Short answer:** with the default configuration, mbedtls runs no concurrent code of its own, and it protects nothing. Its mutex layer is compiled out. Concurrency only exists if the application creates threads and calls into the library from them.

**Why the default build has no mutexes**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, and `MBEDTLS_THREADING_PTHREAD` (line 2196) is also commented out.
- Every mutex use in `library/` sits behind `#if defined(MBEDTLS_THREADING_C)`, and `library/threading.c` is empty of mutex code unless that macro is set.
- The index's `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` values came from an operator flag, not the repo's default. The index's lock and thread results therefore describe a threaded build, not the default one.

**What runs concurrently in the library by default:** nothing. The library creates no threads, installs no signal handlers, and has no timers.

**What runs concurrently in the repository by default:**

| Source | Concurrency | Built by default? |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` (`pthread_create`) | One thread per accepted connection | No. Lines 24–28 print "not defined" and exit unless `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are both set |
| `programs/test/benchmark.c:444` (`SIGALRM` handler) | Async signal context | Only if built |
| `programs/ssl/ssl_server2.c:1698` (`SIGTERM`/`SIGINT` handler) | Async signal context | Only if built |
| Windows `TimerProc` in `benchmark.c:430` | Timer callback thread | Only on Windows, if built |

The index found these four spawn sites. The two signal handlers run in signal context, not on a thread, and they belong to example and test programs, not the library.

**What the mutexes protect when enabled** (`THREADING_C` plus a backend)

- **Per-context locks** in `ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`, `rsa.c`, `ssl_cache.c`, `ssl_cookie.c` and `ssl_ticket.c`. Each `ctx->mutex` serializes access to one shared context object, such as an RNG state, a session cache, or a ticket key set.
- **Global locks** (defined in `threading.c:182–190`):
  - `mbedtls_threading_gmtime_mutex` in `platform_util.c:189` guards the non-reentrant `gmtime()` call.
  - `mbedtls_threading_readdir_mutex` in `x509_crt.c:1611` guards `readdir`.
  - `mbedtls_threading_psa_globaldata_mutex` and `..._psa_rngdata_mutex` guard the PSA global key store and RNG state.
  - `mbedtls_threading_key_slot_mutex` in `psa_crypto.c:2022` guards key-slot allocation.
- **`memory_buffer_alloc.c:63`** has a `heap.mutex` that guards the heap allocator.

**What is not protected, even with threading enabled**

- A single context object used by two threads without the library's lock is still unsafe. The library locks only its internal contexts, not the caller's data.
- The `debug_mutex` in `ssl_pthread_server.c:65` is a program-level lock around the debug callback. It is not part of the library.
- The threading config documentation (`mbedtls_config.h:3740–3780`) says you must enable `MBEDTLS_THREADING_C` before any thread calls a PSA function, and before multi-threaded TLS 1.3 use. This means that without the flag, a default build is only safe if one thread at a time uses the library.

**Limitation on the index's lock result:** it returns one lock identity, `mutex->mutex` in `threading.c`. That is the pthread wrapper's member, not a real protected object, so it does not show what the locks protect. The per-context locks above come from reading the source.