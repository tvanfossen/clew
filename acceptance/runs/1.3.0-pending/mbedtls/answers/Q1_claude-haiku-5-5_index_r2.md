**Short answer:** in a default build, nothing in the library runs concurrently and no mutex is compiled in. The only threads in the repo are in sample programs.

**Why the default build has no locks**

- `include/mbedtls/mbedtls_config.h` has both `MBEDTLS_THREADING_C` (line 3787) and `MBEDTLS_THREADING_PTHREAD` (line 2196) commented out.
- Every mutex call site in `library/` is guarded by `#if defined(MBEDTLS_THREADING_C)`. That covers `ssl_cache.c`, `ssl_ticket.c`, `rsa.c`, `x509_crt.c`, `platform_util.c`, and `error.c`. With the option off, all of that code is absent.
- The index agrees: the lock layer has one identity, `mutex->mutex` in `library/threading.c`, and no two-lock holdings.

**What the threading layer protects when enabled**

`library/threading.c` (guarded by `MBEDTLS_THREADING_C`) has two layers:

- **Function-pointer hooks.** `mbedtls_mutex_init/free/lock/unlock` are global function pointers. With `MBEDTLS_THREADING_PTHREAD` they point at pthread implementations (lines 101–104). Without a backend they point at dummy init/free and at `threading_mutex_fail` for lock/unlock (lines 125–128). I read only lines 101–128 and did not confirm the exact `#else` branch that selects the fail variant. `threading_set_alt()` (around line 138) replaces the hooks with a platform's own mutex.
- **Process-global mutexes**, initialised in `threading_mutex_init` (lines 144–152) and freed at teardown:
  - `readdir` mutex: serialises `readdir` in `x509_crt.c` (around line 1610), where directory-based CA loading is not thread-safe.
  - `gmtime` mutex: serialises the non-reentrant `gmtime` fallback in `platform_util.c` (around line 188).
  - `key_slot` mutex: PSA key-slot management.
  - `psa_globaldata` mutex: PSA global state.
  - `psa_rngdata` mutex: the PSA RNG state.

**What's protected per object (when enabled)**

- `ssl_cache.c`: `cache->mutex` guards the session cache's get, set and free paths.
- `ssl_ticket.c`: `ctx->mutex` guards ticket key rotation and lookup.
- `rsa.c`: `ctx->mutex` guards RSA context state (around line 1238).

I did not enumerate every per-object mutex. The grep was capped at 80 lines, so other users (for example in ECP or PSA) may exist.

**Threads in the repo**

Clew's thread layer finds four spawn sites, all under `programs/`: `ssl_pthread_server.c` (per-connection threads), `benchmark.c` (alarm timer and signal handler), and `ssl_server2.c` (signal handler). None are in `library/`. The library itself spawns nothing, so the library's concurrency contract is "caller's problem": a multithreaded application must enable `MBEDTLS_THREADING_C` plus a backend, or serialise access itself.

**Caveat on the index.** The lock layer records only direct `mutex->mutex` acquisitions. Acquisitions through the `mbedtls_mutex_lock(&x->mutex)` function pointers are not modelled, so the lock count understates the real usage. Treat the per-object list above as read from source, not from the index.