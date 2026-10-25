**Short answer:** In the default configuration, Mbed TLS creates no threads and compiles out every mutex. Nothing inside the library is protected. Concurrency exists only if your application calls the library from several threads, and then the library's shared state is unguarded.

## What runs concurrently

Nothing inside the library. Mbed TLS never creates threads. Any concurrency comes from the application calling into it from multiple threads.

## Why nothing is protected by default

Every lock call in the library sits under `#if defined(MBEDTLS_THREADING_C)`. That option is commented out in the default config:

- `include/mbedtls/mbedtls_config.h:3787`: `//#define MBEDTLS_THREADING_C`
- `:2185` (`MBEDTLS_THREADING_ALT`) and `:2196` (`MBEDTLS_THREADING_PTHREAD`) are also off.
- The CMake build has no threading flags, so it inherits the same defaults.

With `THREADING_C` off, `library/threading.c` compiles to nothing, and the mutex code in `entropy.c`, `ctr_drbg.c`, `psa_crypto.c`, `ssl_cache.c` and the rest is absent.

Enabling `THREADING_C` alone is a build error. `check_config.h:1007-1008` requires exactly one implementation (`PTHREAD` or `ALT`), so a user has to choose one as well.

## What the mutexes protect when enabled

| Mutex | Protects | Where |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key slot table: allocation and read-lock counts | `psa_crypto.c`, `psa_crypto_slot_management.c` |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global init flags, driver-wrapper state | `psa_crypto.c:141-165`, `psa_crypto_slot_management.c:200` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state, fork-reseed check | `psa_crypto.c:130-137`, `psa_crypto_random.c:147` |
| `ctx->mutex` (per context) | Entropy pool and sources | `entropy.c:32`, `:92`, `:178`, `:253` |
| `ctx->mutex` (per context) | CTR-DRBG and HMAC-DRBG state | `ctr_drbg.c:548`, `hmac_drbg.c:107` |
| `ctx->mutex` (per context) | Shared session cache, ticket keys, cookie secret | `ssl_cache.c:31`, `ssl_ticket.c:40`, `ssl_cookie.c` |
| `heap.mutex` | Global heap, only with the buffer allocator | `memory_buffer_alloc.c:540-571` |
| `mbedtls_threading_gmtime_mutex` | `gmtime()` fallback, only on non-POSIX builds | `platform_util.c:188-204` |
| `mbedtls_threading_readdir_mutex` | Directory reads in cert loading, with `MBEDTLS_FS_IO` | `x509_crt.c:1610` |

Most of these are per-object locks. The PSA locks are the only process-wide ones. The per-context locks protect a single object's state; they do not make a shared `mbedtls_ssl_context` safe to use from two threads.

## The risky default

PSA is on by default (`mbedtls_config.h:3334`). TLS 1.3 is also on by default (`:1885`), and it uses PSA directly. Its doc comment says a multithreaded application must enable `MBEDTLS_THREADING_C` (`mbedtls_config.h:1875-1880`). Even so, the default is off.

So a multithreaded application using the default config can hit unguarded PSA global state (key slots, RNG, init flags) through TLS 1.3 handshakes. The config comments say this is unsafe. The default config does not enforce it.

## What I did not verify

I read the source and config but did not build or run anything, so the claims above come from reading code, not from a test. I did not check whether the buffer allocator is enabled by default.