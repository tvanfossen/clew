## What runs concurrently: nothing, by default

mbedtls doesn't spawn threads itself — there's no `pthread_create`/`std::thread`/`CreateThread` anywhere in `library/`. It is a passive library; any concurrency in a program using it comes entirely from the *application* creating threads and calling into mbedtls/PSA from more than one of them.

## The mutex layer is compiled out entirely

In the shipped default `include/mbedtls/mbedtls_config.h`:

```
2185://#define MBEDTLS_THREADING_ALT
2196://#define MBEDTLS_THREADING_PTHREAD
3787://#define MBEDTLS_THREADING_C
```

All three are commented out. That has a cascading effect:

- `library/threading.c`'s entire body sits under `#if defined(MBEDTLS_THREADING_C)`. With it undefined, the file compiles to an essentially empty translation unit — the `mbedtls_mutex_init/free/lock/unlock` function pointers aren't even defined.
- Every single call site that would take a lock is wrapped in the same guard, e.g.:
  - `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `rsa.c` — per-context mutex around entropy/DRBG/RSA state
  - `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c` — session cache / cookie / ticket context locks
  - `x509_crt.c` — `mbedtls_threading_readdir_mutex` around `readdir()`
  - `psa_crypto.c`, `psa_crypto_slot_management.c`, `psa_crypto_random.c` — PSA global-data mutex, RNG-data mutex, key-slot mutex
  - `platform_util.c` — `mbedtls_threading_gmtime_mutex` around the `gmtime()` fallback
  - `memory_buffer_alloc.c` — heap-allocator mutex

So under default configuration, none of these locks/unlocks are even present in the compiled binary — they're dead code paths, not runtime no-ops. **Nothing is protected**, because there is nothing to protect against: the default build gives no thread-safety guarantee at all.

The header comments make this an explicit contract, not an oversight — `mbedtls_config.h` warns at the `MBEDTLS_SSL_PROTO_TLS1_3`, `MBEDTLS_USE_PSA_CRYPTO`, and `MBEDTLS_PSA_CRYPTO_C` options that if you touch these from multiple threads you **must** enable `MBEDTLS_THREADING_C` yourself (and then also `MBEDTLS_THREADING_PTHREAD` or provide `MBEDTLS_THREADING_ALT`) — mbedtls assumes single-threaded use, or at minimum non-shared contexts, unless the integrator opts in.

**Bottom line:** as shipped, mbedtls is a single-threaded-use library. The mutex/thread code exists in source but is entirely conditional; turning on concurrent use of shared contexts without enabling `MBEDTLS_THREADING_C` + a backend is undefined behavior, not "protected but slow."
