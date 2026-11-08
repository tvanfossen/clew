**Short answer:** with the default `mbedtls_config.h`, the library starts no threads and takes no locks. Any concurrency comes from the application calling into the library from several threads, and most of the library's internal state is then unprotected.

**What is off by default**

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`). `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also commented out (lines 2185, 2196).
- So `library/threading.c` compiles to nothing, and the `mbedtls_mutex_*` function pointers in `threading.h` are not declared.
- Every mutex call site is wrapped in `#if defined(MBEDTLS_THREADING_C)`, so none of them exist in the default build.
- I found no `pthread_create` or thread creation anywhere in `library/` or `include/`.

**What is enabled by default and would run concurrently under application threads**

| Enabled by default | Why it matters |
|---|---|
| `MBEDTLS_PSA_CRYPTO_C` | PSA has process-global state: `global_data` (RNG state, init flags) and the key-slot table. |
| `MBEDTLS_SSL_PROTO_TLS1_3` | TLS 1.3 calls PSA directly, so a handshake may call `psa_crypto_init()` even if TLS 1.2 is negotiated (`mbedtls_config.h` ~1858–1885). |
| `MBEDTLS_ENTROPY_C`, `MBEDTLS_CTR_DRBG_C` | Shared entropy/DRBG contexts. |
| `MBEDTLS_SSL_SRV_C`, `MBEDTLS_SSL_CLI_C`, `MBEDTLS_SSL_TLS_C` | TLS contexts, session cache and tickets. |

**What protects what, when THREADING_C is on**

| Lock | Protects |
|---|---|
| Per-context `ctx->mutex` in `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c` | Each DRBG/entropy context's internal state. |
| Per-object mutexes in `ssl_cache.c`, `ssl_ticket.c` | The cache and ticket key state. |
| `heap.mutex` in `memory_buffer_alloc.c` | The heap, only when `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is enabled. It is off by default. |
| `mbedtls_threading_psa_globaldata_mutex` / `psa_rngdata_mutex` | `global_data` in `psa_crypto.c` and the RNG state in `psa_crypto_random.c`. |
| `mbedtls_threading_key_slot_mutex` | Key-slot reservation in `psa_crypto.c`. |
| `gmtime`/`readdir` mutexes | Non-reentrant libc wrappers, in `platform_util.c` and the programs. |

**Consequences with defaults**

- Two threads sharing one `ctr_drbg`, `entropy` or `hmac_drbg` context is a data race.
- Two threads calling any PSA function, including through TLS 1.3 handshakes, race on `global_data` and the key-slot table. The config doc requires THREADING_C for this case.
- Even with THREADING_C on, the locks only cover the listed internals. The config doc says an individual TLS, X.509 or PK context must not be used from two threads at once unless the application synchronises access. I did not trace `mbedtls_ssl_context` access to confirm this beyond that doc text.
- The `programs/ssl/ssl_pthread_server.c` sample is application code that depends on THREADING_C. The library does not create that concurrency.

**Caveat**

I checked the header defaults, not the build system. I did not confirm that `CMakeLists.txt` or the Makefile leaves `MBEDTLS_THREADING_C` undefined, and a build-time config override would change this answer.