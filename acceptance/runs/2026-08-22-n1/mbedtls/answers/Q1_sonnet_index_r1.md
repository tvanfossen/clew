## Default configuration: threading is entirely compiled out

`MBEDTLS_THREADING_C`, `MBEDTLS_THREADING_PTHREAD`, and `MBEDTLS_THREADING_ALT` are all commented out in `include/mbedtls/mbedtls_config.h` (lines ~2185, ~2196, ~3787). None of the three is on by default.

That matters more than a typical "feature flag off" because `library/threading.c` in its entirety sits behind `#if defined(MBEDTLS_THREADING_C)`. With the default config, that file compiles to nothing — the pthread-backed mutex implementation, the `mbedtls_mutex_init/free/lock/unlock` function pointers, and the `mbedtls_threading_mutex_t` type itself simply don't exist in the build. It isn't that locks become no-ops; the lock/unlock call sites aren't there at all.

I confirmed every single mutex call site in the library is wrapped the same way (`#if defined(MBEDTLS_THREADING_C)` around the call, not just the declaration) — checked across `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `rsa.c`, `memory_buffer_alloc.c`, `platform_util.c`, `psa_crypto.c`, `psa_crypto_slot_management.c`, `psa_crypto_random.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, and `x509_crt.c`. So with the default config, the answer to "what protects what" is **nothing protects anything, because there is nothing to protect it with.**

## What actually runs concurrently: nothing, from mbedtls's own code

The index's thread-spawn scan finds exactly two spawn sites in the whole repo, and both are outside the library:

- `programs/ssl/ssl_pthread_server.c` — the example pthreaded server demo, spawns `handle_ssl_connection` per connection.
- `programs/test/benchmark.c` — a Win32 timer thread (`TimerProc`) used for benchmarking, not a worker thread.

The library itself (`library/*.c`) never calls `pthread_create` or any thread-spawn primitive. mbedtls is a passive, call-in library — it has no threads of its own; concurrency exists only if the *integrating application* creates threads and calls into mbedtls from more than one of them.

## The actual default threat model

The library's own documentation states this plainly (`mbedtls_config.h` around the `MBEDTLS_THREADING_C` doc comment): mbedtls assumes a non-threaded environment, or that **contexts are never shared across threads**. That's the real contract, and it's caller-enforced, not library-enforced:

- Two threads each holding their own independent `mbedtls_ssl_context` / `mbedtls_x509_crt` / `mbedtls_ctr_drbg_context` etc. is fine and requires nothing — there's no shared mutable state between separate contexts.
- Two threads touching the *same* context, or any PSA call (`psa_xxx()`) from more than one thread, or any TLS/X.509/PK call when `MBEDTLS_USE_PSA_CRYPTO` is on, or a TLS 1.3 connection at all — is a data race by construction in the default config, because the mutexes that would serialize it don't exist in the binary.

## What the mutexes would protect, if you turned threading on

For context, since the shipped mutex code is real and worth understanding even though it's dormant by default — enabling `MBEDTLS_THREADING_C` plus either `MBEDTLS_THREADING_PTHREAD` (POSIX mutex backend, in `threading.c`) or `MBEDTLS_THREADING_ALT` (caller supplies its own lock callbacks via `mbedtls_threading_set_alt`) activates these critical sections:

| Mutex | Protects |
|---|---|
| `ctr_drbg_context.mutex`, `hmac_drbg_context.mutex` | DRBG internal state during reseed/generate |
| `entropy_context.mutex` | Entropy pool gather/read |
| `rsa_context.mutex` | Blinding state during RSA private-key ops |
| `heap.mutex` (memory_buffer_alloc) | The alternative heap allocator's free-list |
| `mbedtls_threading_gmtime_mutex` (platform_util) | Non-reentrant libc `gmtime`/`localtime` calls where no `gmtime_r` exists |
| `mbedtls_threading_psa_rngdata_mutex`, `mbedtls_threading_psa_globaldata_mutex`, `mbedtls_threading_key_slot_mutex` (psa_crypto*) | PSA's global RNG state, global subsystem/driver state, and per-key-slot state — this is the "PSA has an implicit shared context" case the docs call out as requiring threading even for single-context use |
| `ssl_cache_context.mutex`, `mbedtls_ssl_cookie_context.mutex`, `mbedtls_ssl_ticket_context.mutex` | Session cache / DTLS cookie / session-ticket state shared across connections |
| `mbedtls_threading_readdir_mutex` (x509_crt) | Serializes `readdir()` when loading a certificate directory, since it's non-reentrant on some platforms |

But again — as shipped by default, `MBEDTLS_THREADING_C` is off, so this table describes dead code, not running behavior. Anyone linking mbedtls into a multithreaded app with the default `mbedtls_config.h` and sharing contexts (or using PSA/TLS 1.3 from multiple threads) is relying on nothing but luck.
