**Short answer:** in the default configuration, nothing inside Mbed TLS is protected by a mutex, and the library starts no threads. Its contexts and global state are unsynchronised. Any concurrency comes from the application, and the application has to provide all the protection.

**Why the default is unprotected**

`MBEDTLS_THREADING_C` is commented out in the shipped config (`include/mbedtls/mbedtls_config.h:3787`, `//#define MBEDTLS_THREADING_C`). `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are commented out too (lines 2185 and 2196). Nothing in the top-level or library CMake/Makefile turns them on. Every lock in the library sits behind `#if defined(MBEDTLS_THREADING_C)`, so a default build contains no `mbedtls_mutex_lock` calls and no mutex objects. `programs/ssl/ssl_pthread_server.c` shows the opt-in path.

**What is protected when it is enabled**

| Lock | Protects | Where |
|---|---|---|
| Per-context mutex in `mbedtls_entropy_context` | Source list and accumulator | `library/entropy.c` |
| Per-context mutex in CTR_DRBG and HMAC_DRBG | Generator state during `*_random()` | `library/ctr_drbg.c`, `library/hmac_drbg.c`; the CTR_DRBG mutex is only initialised when an entropy source is set (`include/mbedtls/ctr_drbg.h:221`) |
| Mutex in `ssl_cache`, `ssl_ticket`, `ssl_cookie` | Shared session cache, ticket keys, cookie secret | `library/ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c` |
| Heap mutex | The buffer allocator's free list | `library/memory_buffer_alloc.c` |
| Global `mbedtls_threading_psa_globaldata_mutex` | PSA init state, driver-init flags, key-slot table | `library/psa_crypto.c`, `library/psa_crypto_slot_management.c` |
| Global `mbedtls_threading_key_slot_mutex` | Key-slot registration and reader counts (`psa_unregister_read_under_mutex`) | `library/psa_crypto_slot_management.c` |
| Global `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state | `library/psa_crypto.c`, `library/psa_crypto_random.c` |
| Global gmtime mutex | `gmtime()` fallback, only when no reentrant `gmtime_r` is available | `library/threading.c`, `library/platform_util.c` |
| Global readdir mutex | Defined under `MBEDTLS_FS_IO` | `library/threading.c` (I did not trace its users) |

The threading layer itself (`library/threading.c`) only supplies the pthread or user-supplied implementation behind `mbedtls_mutex_lock/unlock`. It holds no data of its own beyond the global mutex objects. PSA is the important case: the config docs (`mbedtls_config.h:3740-3790`) say the PSA subsystem has an implicit shared context, so any multi-threaded use of PSA, or of TLS/X.509/PK with `MBEDTLS_USE_PSA_CRYPTO`, needs threading enabled. The same docs also say TLS 1.3 needs it regardless. I did not verify where the TLS 1.3 requirement is enforced in code.

**What this means for a default build**

- Sharing one context across threads without external locking is a data race.
- Calling PSA from more than one thread is a data race on the implicit global key-slot and RNG state.
- The only safe multi-threaded pattern is one context per thread with no shared PSA use, or your own lock around every call.
- To get the library's own locking, define `MBEDTLS_THREADING_C` plus `MBEDTLS_THREADING_PTHREAD` (or `MBEDTLS_THREADING_ALT`). `check_config.h:995-1010` enforces that exactly one implementation is chosen.

I did not build or run anything. The conclusions come from reading the source and the shipped config.