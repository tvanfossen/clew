## What the index shows

**Threads.** The index's thread layer finds exactly two AST-detected spawn sites in the whole repository, and both are in optional, non-default-compiled code:

- `handle_ssl_connection` — spawned via `thread_create`/`pthread_create` at `programs/ssl/ssl_pthread_server.c:277`, inside a **sample program** (`ssl_pthread_server`) that only builds when `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` are both defined.
- `TimerProc` — a Win32 timer callback spawned from `mbedtls_set_alarm` in `programs/test/benchmark.c`, a **benchmark test program**, not library code.

No spawn site exists inside `library/`. The library itself never creates a thread; concurrency, if any, is entirely up to the calling application. So "what runs concurrently" isn't something mbedtls does on its own — it's whatever threads the embedding application creates and then uses to call into the same mbedtls contexts/globals.

**Mutex layer.** `library/threading.c` implements a *pluggable* mutex vtable: `mbedtls_mutex_init/free/lock/unlock` are function pointers (declared `extern` in `include/mbedtls/threading.h`), defaulting to `threading_mutex_init_pthread` / `_free_pthread` / `_lock_pthread` / `_unlock_pthread`, which wrap `pthread_mutex_*`. There's also a `threading_mutex_dummy` (init/free no-op) and `threading_mutex_fail` (lock/unlock always return `MBEDTLS_ERR_THREADING_BAD_INPUT_DATA`) pair for the `MBEDTLS_THREADING_ALT` path, i.e. when a caller wants to fail loudly instead of silently no-op if it forgets to call `mbedtls_threading_set_alt()`.

Five global mutex objects are declared in `threading.h` / defined+initialized (`MUTEX_INIT` = `{PTHREAD_MUTEX_INITIALIZER, 1}`) in `threading.c`:

| Mutex | Protects (by name) |
|---|---|
| `mbedtls_threading_gmtime_mutex` | calls into non-reentrant `gmtime()` |
| `mbedtls_threading_readdir_mutex` | calls into non-reentrant `readdir()` |
| `mbedtls_threading_key_slot_mutex` | the PSA key-slot table |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global crypto state |
| `mbedtls_threading_psa_rngdata_mutex` | PSA global RNG state |

The gate list on `MBEDTLS_THREADING_C` shows this machinery is consumed all over the library — `ctr_drbg.c`, `entropy.c`, `hmac_drbg.c`, `rsa.c`, `x509_crt.c`, `psa_crypto*.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, `memory_buffer_alloc.c`, `debug.c`, `platform_util.c` all have `#if defined(MBEDTLS_THREADING_C)`-gated locking around shared state (RNG contexts, RSA blinding state, session caches, cookie/ticket state, the debug threshold, etc.), each presumably taking one of these mutexes or its own per-object mutex around a specific critical section.

## Where the index can't answer, and why

Two gaps, both explicit in the returned data rather than inferred:

1. **The lock-usage layer only resolved one row**: `mutex->mutex` inside `threading.c` itself (the raw `pthread_mutex_t` member access), with 0 recorded two-lock nestings. The dozens of `mbedtls_mutex_lock(&some_global_mutex)` call sites in `rsa.c`, `psa_crypto*.c`, `ssl_cache.c`, etc. are visible only as consumers of the `MBEDTLS_THREADING_C` gate, not as distinct lock-identity rows — this is a detector limitation (calls through a function pointer aren't resolved to "acquires *this* mutex" the way a direct `pthread_mutex_lock(&x)` would be), not a claim that those sites don't lock anything.

2. **"As configured by default" is unanswerable from this index as built.** Every gate/dossier result for `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` comes back with `origin: "no_definition_site"` and the note that no `config_header` is declared for this target — meaning the index was built without pointing at the repo's actual `mbedtls_config.h`, so it has no record of whether these symbols are `#define`d or commented out there. I'm not going to assert from memory whether `MBEDTLS_THREADING_C` ships on or off by default in this checkout; that's a config-header fact this index wasn't given, and asserting it from training-data recall would be exactly the kind of ungrounded claim to avoid. To get a real answer, either declare `preprocessor.config_header` and rebuild, or read `include/mbedtls/mbedtls_config.h` directly.

**Bottom line (grounded part):** mbedtls's library code never spawns a thread — any concurrency is the embedding application's doing, using multiple threads that call into the same mbedtls objects. The library defends five specific pieces of global state (`gmtime`, `readdir`, PSA key slots, PSA global crypto state, PSA RNG state) with dedicated mutexes, plus scattered per-subsystem locking (RNG contexts, RSA blinding, SSL cache/cookie/ticket state) gated behind `MBEDTLS_THREADING_C`, all routed through a pluggable, swappable mutex vtable rather than hardcoded to pthreads. Whether that gate is actually on in this repo's shipped default config is a fact the index isn't wired to read — that's the honest gap, not a guess.
