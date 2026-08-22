## Short answer

With the shipped default `mbedtls_config.h`, **`MBEDTLS_THREADING_C` is `#undef`'d** (`include/mbedtls/mbedtls_config.h:3787`), and so are both of its backends, `MBEDTLS_THREADING_PTHREAD` (`:2196`) and `MBEDTLS_THREADING_ALT` (`:2185`). That means:

- **No mutex code is compiled in at all.** Every mutex field in a context struct, every `mbedtls_mutex_lock/unlock/init/free` call site, and the entire contents of `library/threading.c` are wrapped in `#if defined(MBEDTLS_THREADING_C)`. With the flag off, `mbedtls_threading_mutex_t` isn't even a defined type, the struct fields (`ctx->mutex` in `rsa.h`, `ctr_drbg.h`, `entropy.h`, `hmac_drbg.h`, `ssl_cache.h`, `ssl_cookie.h`, `ssl_ticket.h`) vanish, and the global mutexes (`mbedtls_threading_readdir_mutex`, `mbedtls_threading_gmtime_mutex`, and the three PSA mutexes) don't exist. `mbedtls_mutex_lock()` isn't a no-op stub — it simply isn't declared.
- **mbedtls never spawns a thread itself, ever, regardless of config.** There's no `pthread_create`/`CreateThread`/`thrd_create` anywhere in `library/`. What ships as "thread code" (`threading.c`, `threading.h`, `threading_internal.h`) is purely a *mutex abstraction* the application can plug into (raw pthreads via `MBEDTLS_THREADING_PTHREAD`, or a custom `threading_alt.h` via `MBEDTLS_THREADING_ALT`) — it's not a scheduler or a source of concurrency.

## So what actually runs concurrently by default?

Nothing, from mbedtls's own perspective — it's single-threaded code with no internal locking. Any concurrency in a default build comes entirely from the **calling application** choosing to invoke mbedtls/PSA APIs from more than one OS thread. Since the library ships with zero internal synchronization in this configuration, that's the app's responsibility, not the library's:

- Calling mbedtls functions on the **same context object** from two threads concurrently (e.g., two threads doing I/O on one `mbedtls_ssl_context`, or two threads reseeding the same `mbedtls_ctr_drbg_context`) is a **data race / undefined behavior** by design — the library documents this (e.g. `ctr_drbg.h:294`, `entropy.h:146` — "thread-safe if `MBEDTLS_THREADING_C` is enabled", implying it is *not* otherwise).
- Calling mbedtls on **separate, independent contexts** from separate threads (e.g., one `mbedtls_ssl_context` per thread, no shared state) is fine, because there's nothing shared to race on — that was always true and doesn't depend on the threading flag.
- The one place this bites even with "independent-looking" objects is anything backed by **process-global state**: PSA's `global_data` (key slots, RNG state), the X.509 `readdir` mutex used by `mbedtls_x509_crt_parse_path()`, and the libc `gmtime()`-guarding mutex in `platform_util.c`. Default config leaves all of these unprotected too, so if the app is multithreaded, using `MBEDTLS_PSA_CRYPTO_C` from multiple threads or parsing a cert directory concurrently is unsafe out of the box.

## What the mutexes protect, when the option is turned on

For completeness, since the question is clearly probing the gap between "ships mutex code" and "default config" — here's what those mutexes guard once `MBEDTLS_THREADING_C` (+ `_PTHREAD` or `_ALT`) is enabled:

| Mutex | Protects |
|---|---|
| Per-context `ctx->mutex` (`ctr_drbg.c`, `hmac_drbg.c`, `rsa.c`, `entropy.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`) | That single context's internal state so it can safely be shared/called from multiple threads |
| `mbedtls_threading_readdir_mutex` | The non-reentrant `readdir()` call in `x509_crt.c`'s directory-parsing path |
| `mbedtls_threading_gmtime_mutex` | The non-reentrant libc `gmtime()` fallback in `platform_util.c` |
| `mbedtls_threading_key_slot_mutex` | `registered_readers`/`state` fields of every PSA key slot (`psa_crypto.c`, `psa_crypto_slot_management.c`) |
| `mbedtls_threading_psa_globaldata_mutex` | All other fields of PSA's `global_data` struct |
| `mbedtls_threading_psa_rngdata_mutex` | PSA's global RNG state (`global_data.rng`/`rng_state`) specifically, split out from the mutex above for less contention |

Note even in this enabled case the granularity is **global-state and single-context protection**, not "safe to hammer any object from any thread" — the caller still owns the invariant that a given `mbedtls_ssl_context`/`mbedtls_x509_crt` isn't mutated by two threads at once unless the specific API says otherwise.

**Bottom line:** as shipped, mbedtls is a single-threaded library with a pluggable mutex abstraction that is dormant by default. If your build is multithreaded and touches mbedtls/PSA from more than one thread, you must explicitly turn on `MBEDTLS_THREADING_C` + a backend, or serialize access yourself — the default config gives you neither.
