**Short answer:** in the default configuration, the library runs nothing concurrently and protects nothing. The mutex layer is compiled out. Any concurrency is whatever the application does, and the library assumes each context is used by one thread at a time.

**Why:** `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`). `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also commented out (lines 2185, 2196). Nothing in the CMake, Makefile, or `library/` build files turns them on. The library never creates threads: no `pthread_create` or `std::thread` appears under `library/` or `include/`. The only pthread use is `programs/ssl/ssl_pthread_server.c`, which is an example program.

**What runs concurrently:** only what the application puts on multiple threads. The library has no background work.

**What protects what, with the default config:**

| Shared state | Protection by default |
|---|---|
| CTR_DRBG, HMAC_DRBG, entropy contexts | None. Each has a `mutex` member and lock/unlock calls, all guarded by `#if MBEDTLS_THREADING_C` (`ctr_drbg.c:702`, `hmac_drbg.c:387`, `entropy.c:92`). They compile out. |
| SSL session cache, cookie, ticket contexts | None (`ssl_cache.c:83`, `ssl_cookie.c:248`, `ssl_ticket.h:33`). |
| Global heap in `memory_buffer_alloc` | None (`memory_buffer_alloc.c:540`). |
| PSA global state (`global_data`, RNG state, key slots) | None. `psa_get_initialized()` reads and writes `global_data` with no lock (`psa_crypto.c:126–150`). The key-slot and RNG paths use the same guard pattern. |
| `gmtime` fallback in `platform_util.c` | None, when the non-reentrant path is used. |

The PSA state matters most. PSA is a process-wide singleton, and `MBEDTLS_PSA_CRYPTO_C` is enabled by default (`mbedtls_config.h:3334`). Two threads calling `psa_crypto_init()` or any PSA function at the same time race on `global_data`. The header comment at `mbedtls_config.h:3740` says you must enable `MBEDTLS_THREADING_C` for any multithreaded use of PSA, TLS 1.3, or PSA-backed TLS/X.509/PK.

**When `MBEDTLS_THREADING_C` is enabled**, the locks are as follows. Each per-context mutex covers only that context. The PSA mutexes are declared in `include/mbedtls/threading.h`:
- `mbedtls_threading_psa_globaldata_mutex` covers the PSA global data other than the RNG.
- `mbedtls_threading_psa_rngdata_mutex` covers the RNG.
- `mbedtls_threading_key_slot_mutex` covers key slots.
- `mbedtls_threading_gmtime_mutex` covers the `gmtime` fallback.

Locks are not shared across these domains. The layer only gives you mutual exclusion on each object. It does not make a single context safe for two threads to use concurrently.

**Practical consequence:** a default build is safe for single-threaded use, or for multithreaded use where every thread owns its own contexts and PSA is initialized once before threads start. Sharing any context, or calling PSA from several threads, requires building with `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`.

I did not build or run the library or test the configurations. These conclusions come from reading the config header and the guards in the source.