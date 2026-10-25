**Short answer:** in the default configuration, the library runs no threads and takes no locks. Mutex code is compiled out, so nothing in mbedtls is protected by a mutex. Any concurrency comes from the application, and the application must synchronize access itself.

**Why:**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, and both `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are commented out too.
- `library/threading.c` is wrapped in `#if defined(MBEDTLS_THREADING_C)`, so with defaults it compiles to nothing. Every `mbedtls_mutex_lock/unlock` call site is guarded by the same macro, so none are compiled in.
- `library/` never calls `pthread_create`. The library creates no threads of its own.
- `check_config.h:1007` makes `MBEDTLS_THREADING_C` alone a build error. You must also pick PTHREAD or ALT.

**What is unprotected by default:**

| Area | Default state | Where it would be protected |
|---|---|---|
| Per-context state: CTR_DRBG, HMAC_DRBG, entropy, RSA, SSL cache, ticket, cookie | Locks are not compiled in | `ctx->mutex` under `MBEDTLS_THREADING_C` (e.g. `ctr_drbg.c:702`, `entropy.c:92`, `ssl_cache.c:83`) |
| PSA global state: key slots, global data, RNG data | Not locked | `mbedtls_threading_key_slot_mutex`, `..._psa_globaldata_mutex`, `..._psa_rngdata_mutex` (`threading.c`, used in `psa_crypto*.c`) |
| Heap allocator (`memory_buffer_alloc`) | Not locked | `heap.mutex` (`memory_buffer_alloc.c:540`) |
| `gmtime` fallback | Not locked | `mbedtls_threading_gmtime_mutex` (`platform_util.c:188`) |
| `readdir` in X.509 path loading | Not locked | `mbedtls_threading_readdir_mutex` (`x509_crt.c:1610`) |

`MBEDTLS_PSA_CRYPTO_C` (line 3334) and `MBEDTLS_FS_IO` (line 1186) are on by default, so the PSA shared state and the readdir and gmtime paths are live even though nothing locks them.

**What the threading design would protect if enabled:** the mutex layer is a function-pointer table. With PTHREAD it uses `pthread_mutex_*`. With ALT, the defaults are dummy/fail stubs until the app calls `mbedtls_threading_set_alt()`. Each mutex guards only its own context or global, so it does not protect against two threads sharing an un-mutexed object elsewhere.

**Doc caveat:** the `MBEDTLS_THREADING_C` comment (`mbedtls_config.h:3740–3780`) says threading support is required for PSA use from more than one thread, for TLS 1.3 connections regardless of configuration, and for TLS/X.509/PK calls with `MBEDTLS_USE_PSA_CRYPTO`. A multithreaded app on the default config is outside what the library supports.

**Caveat on method:** I checked this by reading the source and config, not by building or running. `programs/ssl/ssl_pthread_server.c:24` refuses to run unless PTHREAD and THREADING_C are set, which fits the same conclusion.