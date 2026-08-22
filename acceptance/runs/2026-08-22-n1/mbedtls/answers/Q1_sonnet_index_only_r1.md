## Short answer

By default, **nothing in mbedtls runs concurrently, and no mutex is actually protecting anything** — the threading/mutex layer compiles out entirely, and the library itself never spawns a thread.

## What the index shows

**`MBEDTLS_THREADING_C` is off by default.** The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` force-defined (via an explicit build flag) just so it could see the code behind those `#if` guards — but it explicitly flags that as a build artifact, *not* evidence of the shipped default. The telling fact: for macros that genuinely are on by default (e.g. `MBEDTLS_HAVE_TIME`, `MBEDTLS_PSA_CRYPTO_C`), the index finds a live `#define` site in `include/mbedtls/mbedtls_config.h`. For `MBEDTLS_THREADING_C` it finds **no definition site anywhere in the repo** — the pattern the index says means "commented out in the shipped config."

**Consequence: `library/threading.c` compiles to nothing.** The entire file (lines 18–193, i.e. the whole thing) is gated behind `#if defined(MBEDTLS_THREADING_C)`. That means, in a default build:
- The four indirection function pointers `mbedtls_mutex_init/free/lock/unlock` don't exist.
- The five global mutex objects (`mbedtls_threading_readdir_mutex`, `_gmtime_mutex`, `_key_slot_mutex`, `_psa_globaldata_mutex`, `_psa_rngdata_mutex`) don't exist.
- Nothing calls them, because there's nothing there to call.

**The library spawns zero threads of its own.** Repo-wide, the index finds exactly **two** thread-spawn sites, and neither is in `library/`:
1. `programs/ssl/ssl_pthread_server.c: handle_ssl_connection`, spawned via `pthread_create` — but the whole file is gated `#if defined(MBEDTLS_THREADING_C) && defined(MBEDTLS_THREADING_PTHREAD)`, so it doesn't even build by default. It's a demo app showing how *a caller* might drive multiple `mbedtls_ssl_context` handshakes in parallel threads — not something mbedtls does internally.
2. `programs/test/benchmark.c: TimerProc` — not a real concurrency thread at all; it's a Win32 one-shot timer callback used to implement the benchmark tool's alarm/timeout, gated behind `_WIN32`/`EFI32`/`EFIX64`. Irrelevant on a default POSIX build, and it's a test utility, not library code.

So on a default config/build, mbedtls is inert with respect to concurrency — it's designed to be called from whatever threading model the embedding application chooses, and does no locking on its own.

## What the mutexes protect, *if* you turn threading on

If an integrator explicitly enables `MBEDTLS_THREADING_C` plus a backend (`MBEDTLS_THREADING_PTHREAD` or `MBEDTLS_THREADING_ALT`), the five global mutexes each guard one specific piece of **process-wide shared state**, not a struct instance:

| Mutex | Guards | Active when |
|---|---|---|
| `mbedtls_threading_readdir_mutex` | non-reentrant `readdir()` (x509 cert-directory loading) | `MBEDTLS_FS_IO` |
| `mbedtls_threading_gmtime_mutex` | non-reentrant `gmtime()` (cert time validation) | `THREADING_USE_GMTIME` |
| `mbedtls_threading_key_slot_mutex` | the PSA key-slot table (used by `psa_get_and_lock_key_slot*`, `psa_close_key`, `psa_purge_key`) | `MBEDTLS_PSA_CRYPTO_C` (on by default, but inert without threading) |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global crypto-subsystem state | `MBEDTLS_PSA_CRYPTO_C` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA global RNG state | `MBEDTLS_PSA_CRYPTO_C` |

Caveat on precision: the index's lock-tracking layer only resolved **one** distinct lock identity repo-wide — a low-confidence `mutex->mutex` member expression inside the generic `threading_mutex_lock_pthread`/`unlock_pthread` wrappers in `threading.c`. All five globals funnel through that same generic wrapper, so the index can't hand me a distinct acquisition count per mutex — only that each is a separately declared/initialized global, referenced by name at specific call sites in the x509 and PSA crypto code shown above.

One thing worth noting from the same evidence: across the whole repo the lock corpus found only that one generic identity — no per-object locking around `mbedtls_ssl_context`, `mbedtls_x509_crt`, or PSA key handles. So even with threading enabled, this layer only makes a handful of *global* data structures safe to touch from multiple threads; it does not make it safe to share one SSL context or X.509 struct across threads without the caller doing its own locking.
