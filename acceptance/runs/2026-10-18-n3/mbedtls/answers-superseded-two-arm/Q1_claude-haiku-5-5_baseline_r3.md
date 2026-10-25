**Short answer:** in the default configuration the library has no mutexes at all, and it creates no threads. Whatever runs concurrently is whatever your application runs on its own threads, and nothing inside the library protects the shared state.

## Why the default build has no locks

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`).
- Neither `MBEDTLS_THREADING_PTHREAD` (line 2196) nor `MBEDTLS_THREADING_ALT` (line 2185) is enabled.
- Every `mbedtls_mutex_lock/unlock` call site is wrapped in `#if defined(MBEDTLS_THREADING_C)`. In the default build those calls compile out.

## Shared state that is unprotected by default

Defaults that matter here: `PSA_CRYPTO_C`, `SSL_CACHE_C`, `SSL_TICKET_C`, `ENTROPY_C`, `CTR_DRBG_C` and `SSL_PROTO_TLS1_3` are all on. `USE_PSA_CRYPTO` is off.

| Shared state | Location | Default protection |
|---|---|---|
| PSA global init state and RNG state | `library/psa_crypto.c` (`global_data`, ~l.120–170) | None |
| PSA key slots | `library/psa_crypto_slot_management.c` | None |
| Entropy sources and accumulator | `library/entropy.c` | None |
| CTR_DRBG / HMAC_DRBG state | `ctr_drbg.c`, `hmac_drbg.c` | None |
| Session cache entries | `library/ssl_cache.c` | None |
| Session ticket keys | `library/ssl_ticket.c` | None |
| `gmtime` wrapper | `library/platform_util.c` | None |

## What the mutexes protect when enabled

With `MBEDTLS_THREADING_C` plus one implementation enabled:

- **`mbedtls_threading_key_slot_mutex`** guards PSA key slots.
- **`mbedtls_threading_psa_globaldata_mutex`** guards the PSA init flags and global data.
- **`mbedtls_threading_psa_rngdata_mutex`** guards the PSA RNG state.
- **Per-context `mutex`** in entropy, CTR_DRBG and HMAC_DRBG guards that context's state. Only the context is locked, not the caller's other data.
- **Per-context `mutex`** in the session cache and ticket context guards their entries and keys.
- **`mbedtls_threading_gmtime_mutex`** serialises time conversion where `gmtime_r` isn't guaranteed.
- **`mbedtls_threading_readdir_mutex`** serialises directory reads when `FS_IO` is on.

Per-object mutexes only help when the same object is shared. Two threads each using their own `mbedtls_ssl_context` never contend on one of these locks, except where they hit the global PSA state.

## The surprise: TLS 1.3 under defaults

`mbedtls_config.h` (threading doc, ~l.3740–3770) says threading must be enabled for "a TLS 1.3 connection, regardless of the compile-time configuration", and for any PSA call from more than one thread. TLS 1.3 is on by default and PSA is always on, so a default build running TLS 1.3 on two threads is outside the library's stated thread-safety. The unlocked PSA global state and key slots are the shared resources involved.

## To make it thread-safe

Enable `MBEDTLS_THREADING_C` and exactly one of `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`. `include/mbedtls/check_config.h:995–1010` enforces that rule. Also call `mbedtls_threading_set_alt()` or initialise PSA before starting threads.

This is a static reading of the source. I did not build the library or run any tests.