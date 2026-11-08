**Short answer:** in the default configuration the library runs nothing concurrently and protects nothing. It has no mutexes at all. Every lock in the tree is compiled out, and the library creates no threads, so any concurrency is whatever your application does on top of it.

**Why the locks vanish by default**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787`. The header gates the mutex API in `include/mbedtls/threading.h:105` on that symbol, and `threading.c` is also built only under it.
- The PSA lock macros (`PSA_THREADING_CHK_RET` / `_GOTO_EXIT` in `library/psa_crypto_core.h:143+`) are defined only under `MBEDTLS_THREADING_C`, so the PSA lock call sites compile to nothing.
- The per-context locks (`ctx->mutex` in entropy, ctr_drbg, hmac_drbg, rsa, ssl_cache, ssl_cookie, ssl_ticket, and the heap lock in memory_buffer_alloc) follow the same guard pattern.
- Even with `THREADING_C` on, you still need a backend: `MBEDTLS_THREADING_PTHREAD` (`mbedtls_config.h:3783-2196`) or `MBEDTLS_THREADING_ALT`. Both are off by default.

**What runs concurrently by default:** nothing inside the library. Concurrency only occurs if your application calls into the library from several threads.

**What is enabled by default, and therefore exposed:**

| Module | Default | Shared state with no lock |
|---|---|---|
| PSA crypto (`MBEDTLS_PSA_CRYPTO_C`, line 3334) | on | `global_data` (init flags, RNG state, driver init), the key-slot table and reader counts, the RNG context |
| Entropy, CTR_DRBG | on (2895, 2757) | the entropy source list and DRBG state |
| SSL session cache, cookie, ticket | on (3670, 3680, 3693) | the session cache, cookie secrets, ticket keys |

**What the locks would protect when enabled** (`THREADING_C` plus a backend):

- **PSA global data:** `rngdata_mutex` guards the RNG context. `globaldata_mutex` guards the init and driver state. `mbedtls_threading_key_slot_mutex` guards the key-slot table and the reader counts. `psa_crypto_core.h` says the caller must hold this last one before checking `registered_readers`.
- **Per-context:** each DRBG, entropy, RSA, SSL cache, cookie and ticket context has its own mutex. A context is locked for the duration of an operation, not for the lifetime of the object.
- **Heap:** `memory_buffer_alloc` locks `heap.mutex` around allocations.
- **`gmtime`:** `platform_util.c:189` locks a global mutex, but this matters only on the non-POSIX `gmtime_r` fallback.

**Consequences for you:**

- A default build used from two threads has data races on PSA's global state, on any shared SSL session cache, and on any shared DRBG or entropy context. Nothing will tell you.
- If the same PSA key or context is used from two threads, the `THREADING_C` documentation says it must be enabled. The default configuration does not do this for you.
- Turning on `MBEDTLS_THREADING_C` alone is not enough. You must also select a backend, or the build will fail.

I did not build the library or run a threaded test. These conclusions come from reading the configuration and the guard macros.