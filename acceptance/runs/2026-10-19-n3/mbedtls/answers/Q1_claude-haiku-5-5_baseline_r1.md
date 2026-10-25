**Short answer:** by default, nothing in the library runs concurrently with anything else, and nothing is protected by a mutex. `MBEDTLS_THREADING_C` is commented out in the default config (`include/mbedtls/mbedtls_config.h:3787`), so every `#if defined(MBEDTLS_THREADING_C)` block is compiled out and `library/threading.c` contributes no code. The library is written for single-threaded use or for contexts that are never shared between threads.

**What runs concurrently**

- Nothing inside mbedtls creates threads. Any concurrency comes from the application, which may call into the library from several threads.
- The library's own state is unprotected. This includes the PSA subsystem's shared `global_data` (RNG state, key slots, init flags). The header says PSA has an "implicit shared context", so two threads calling `psa_*` or any PSA-backed `mbedtls_ssl_*`/`x509`/`pk` code can race.
- The docs (`mbedtls_config.h` around line 1870) also say a TLS 1.3 connection needs `MBEDTLS_THREADING_C` even if you never share it, because TLS 1.3 goes through PSA.

**What the mutexes protect when enabled**

You must enable `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT` (`check_config.h:995–1008` enforces this).

| Mutex / object | Protects |
|---|---|
| `mbedtls_threading_key_slot_mutex` (`threading.h`) | PSA key-slot state and reader counts; held across key destruction so a key can't be reloaded mid-delete |
| `mbedtls_threading_psa_globaldata_mutex` | PSA `global_data` members other than RNG |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state and RNG struct |
| `mbedtls_threading_readdir_mutex` | `readdir`, when `MBEDTLS_FS_IO` is on |
| `mbedtls_threading_gmtime_mutex` | the `gmtime_r` fallback on non-POSIX platforms |
| per-object `mutex` in `mbedtls_entropy_context`, `mbedtls_ctr_drbg_context`, `mbedtls_ssl_cache_context`, `mbedtls_ssl_ticket_context`, `mbedtls_ssl_cookie_ctx` | that object's internal state, locked inside each API call |

**What is not protected, even when threading is on**

- An individual `mbedtls_ssl_context`, or any other per-connection context, has no mutex. Sharing one across threads still needs application locking.
- Configuration and setup calls (for example `mbedtls_threading_set_alt()`) must happen before any other library call.

**Practical reading:** the default build is a single-threaded library. If your app is multithreaded, you must enable threading, and the header's list of cases requiring it (PSA calls, TLS 1.3 connections, shared contexts) is the checklist to apply. I checked this by reading the headers and sources. I did not build or run the library.