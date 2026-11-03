**Short answer:** in the default configuration, the library runs no threads and takes no locks. Any concurrency comes from the application calling into it from several threads. Nothing protects the shared PSA state, so the application must serialize access itself.

**Why:**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, and neither `MBEDTLS_THREADING_PTHREAD` nor `MBEDTLS_THREADING_ALT` is enabled (lines 2185, 2196). `library/threading.c` compiles to nothing without `MBEDTLS_THREADING_C`.
- Every mutex use in the library is wrapped in `#if defined(MBEDTLS_THREADING_C)`. That covers the PSA, SSL cache, entropy, DRBG and gmtime paths. In the default build all of them are compiled out.
- `grep` finds no `pthread_create` or other thread creation in `library/`.

**What is shared, and what protects it when the option is off:**

| Shared state | Location | Default protection |
|---|---|---|
| PSA global data (init state, drivers) | `psa_crypto.c`, static `global_data` | None |
| PSA RNG state | `psa_crypto.c`, `global_data.rng` | None |
| PSA key slots | `psa_crypto_slot_management.c`, static slot array | None |
| SSL session cache | `ssl_cache.c`, `cache->mutex` | None (mutex compiled out) |
| Entropy context | `entropy.c` | None |
| Heap allocator | `memory_buffer_alloc.c` (only if `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is enabled, which is not the default) | None |
| gmtime fallback | `platform_util.c` | None |

Per-object contexts (SSL, X.509, PK, cipher and hash contexts) are not protected in any configuration. The rule is that one thread owns a context at a time. The mutex layer only matters for the shared state above, plus contexts you deliberately share.

**The gap that matters:** `mbedtls_config.h` (lines 3740–3783) says you must enable `MBEDTLS_THREADING_C` if more than one thread uses any PSA function, or any TLS/X.509/PK function when `MBEDTLS_USE_PSA_CRYPTO` is on. It also says a TLS 1.3 connection needs it regardless of configuration. The default build has `MBEDTLS_PSA_CRYPTO_C` and `MBEDTLS_SSL_PROTO_TLS1_3` enabled (lines 3334, 1885) and `MBEDTLS_THREADING_C` disabled. So a multithreaded application using default TLS 1.3 or PSA will race on the global PSA state and the key slots with no lock to stop it. I read this from the source and the config comments; I did not build or run a race test.

**If you need concurrency:** enable `MBEDTLS_THREADING_C` plus `MBEDTLS_THREADING_PTHREAD` (or supply `MBEDTLS_THREADING_ALT`), then call `mbedtls_threading_set_alt()` or rely on the pthread default. Otherwise, serialize all PSA and TLS calls behind one application-level lock.