**Short answer:** In the default configuration, the library runs no threads of its own and takes no locks. Mutex and thread code is compiled out, so all protection is the application's job.

**Why:** `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`). Every mutex call in the library sits under `#if defined(MBEDTLS_THREADING_C)`. `library/threading.c` is empty of code unless that macro is set. `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also off (lines 2185, 2196). `pthread_create` appears nowhere under `library/`; the only pthread code I found is `programs/ssl/ssl_pthread_server.c`, which is an example program.

**What runs concurrently:** Nothing inside the library. Concurrency comes only from the application, for example several threads each driving their own SSL connection. The library assumes either one thread per context or no sharing. The docs say the same: `mbedtls_config.h:3740-3760` requires `MBEDTLS_THREADING_C` for any multithreaded use of PSA, of TLS/X.509/PK when PSA is used, or of a shared crypto context.

**What the mutexes would protect if enabled:**

| Scope | Mutex | Protects |
|---|---|---|
| Global | `mbedtls_threading_key_slot_mutex` | PSA key-slot table and read counts (`psa_crypto.c` ~1305–2045) |
| Global | `mbedtls_threading_psa_globaldata_mutex` | PSA global state (`psa_crypto.c` ~140–166) |
| Global | `mbedtls_threading_psa_rngdata_mutex` | PSA RNG/DRBG reseed and generate (`psa_crypto.c` ~8029–8084) |
| Global | `mbedtls_threading_readdir_mutex` | `readdir` (only with `MBEDTLS_FS_IO`, which is on) |
| Global | `mbedtls_threading_gmtime_mutex` | `gmtime()` fallback, used only when `gmtime_r` is unavailable (`platform_util.c:188-204`) |
| Per-context | `mutex` in entropy, CTR-DRBG, HMAC-DRBG, RSA blinding, SSL cache, SSL cookie, SSL ticket | Each context's internal state (e.g. `entropy.c` ~93–113) |

**What that means by default:**
- The PSA global state (`static psa_global_data_t global_data`, `psa_crypto.c:124`), the key slots, and the PSA RNG are unlocked. Concurrent PSA calls from two threads can race.
- Sharing one entropy, DRBG, `ssl_cache`, `ssl_cookie` or `ssl_ticket` context across threads is unsafe. Those contexts have no lock.
- The `gmtime` lock is not an issue on Linux, because the default path calls `gmtime_r` (`platform_util.c:184`).

**Gotcha:** PSA is on (`mbedtls_config.h:3334`) and TLS 1.3 is on (`:1885`), so a default build is in the category the library's own docs say needs `MBEDTLS_THREADING_C` for multithreaded use. `check_config.h:995-1010` only enforces that the threading implementations require `THREADING_C`. Nothing forces `THREADING_C` on when PSA or TLS 1.3 is enabled.

**To make it thread-safe:** Define `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` or your own `MBEDTLS_THREADING_ALT`. Then build the library with that config.

**Not checked:** I did not confirm whether TLS 1.3 uses PSA internally under the default config (`MBEDTLS_USE_PSA_CRYPTO` is off by default). I also did not check whether the pthread example enables threading in its own build config.