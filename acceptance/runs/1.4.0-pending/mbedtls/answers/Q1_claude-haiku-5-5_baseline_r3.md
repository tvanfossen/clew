**Short answer:** in the default configuration, mbedtls compiles out all of its locking. Nothing inside the library runs concurrently, and nothing protects anything. The library assumes that contexts are not shared across threads, and the one global it does have (PSA state) is unprotected.

**Why the default build has no locks**

- `MBEDTLS_THREADING_C` is commented out at `include/mbedtls/mbedtls_config.h:3787`.
- Every mutex field, lock call, and the `mbedtls_mutex_*` function pointers are inside `#if defined(MBEDTLS_THREADING_C)`. I checked the guards at the call sites in `ssl_cache.c`, `ssl_ticket.c`, `rsa.c`, `hmac_drbg.c`, `entropy.c`, `psa_crypto*.c`, `x509_crt.c`, and `memory_buffer_alloc.c`.
- Enabling it takes two settings, not one. `check_config.h:995-1010` requires `MBEDTLS_THREADING_C` plus exactly one of `MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`, and both of those are also off by default.

**What runs concurrently**

Only what the application starts. The library creates no threads. In the default build, each context has no internal protection, so the rule is:

| Usage | Safe? |
|---|---|
| Each thread uses its own `ssl`/`rsa`/`ctr_drbg`/`entropy` context | Yes, as far as the library goes |
| Several threads share one context object | No |
| Several threads share the PSA global state (key store, RNG, key slots) | No. Protection exists only when `THREADING_C` is on |

**What is protected when `THREADING_C` + pthread is enabled**

Each lock sits next to the state it guards:

| Lock | Protects |
|---|---|
| Per-context `mutex` in `ssl_cache`, `ssl_ticket`, `hmac_drbg`, `entropy`, `memory_buffer_alloc` heap | That object's internal state |
| `rsa.c` per-context mutex around the blinding values (lines ~1239, ~1518) | Blinding state used during private-key operations |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state, including the post-`fork()` reseed in `psa_crypto_random.c` |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global data, used in `psa_crypto.c` |
| `mbedtls_threading_key_slot_mutex` | PSA key slots (`psa_crypto_slot_management.c`) |
| `mbedtls_threading_readdir_mutex` | `readdir()` in `x509_crt` path loading, which is not reentrant |
| `mbedtls_threading_gmtime_mutex` | Fallback `gmtime` path |

**The gap in the default configuration**

- PSA crypto is on (`MBEDTLS_PSA_CRYPTO_C`), and TLS 1.3 is on (`mbedtls_config.h:1885`).
- The `MBEDTLS_THREADING_C` documentation (`mbedtls_config.h` ~3740-3770) says that a TLS 1.3 connection requires threading "regardless of the compile-time configuration", and that any PSA call from more than one thread requires it too.
- So the default build is outside its own documented contract for any multithreaded application that does TLS 1.3 or PSA calls. The PSA global key store and RNG are the shared state that is actually exposed.

**Limits of this check**

I read the source and the config but did not build or run anything. I did not confirm by execution that the default TLS 1.3 path reaches PSA global state, though the config documentation says it does. I also did not look at `ctr_drbg.c`'s lock sites in detail; grep shows it is guarded by `THREADING_C` like the others.