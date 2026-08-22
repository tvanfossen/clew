## Short answer

**As shipped, by default: nothing runs concurrently, and nothing is protected — the entire mutex layer is compiled out.**

`MBEDTLS_THREADING_C` is disabled by default (`//#define MBEDTLS_THREADING_C` in `include/mbedtls/mbedtls_config.h:3787`), and so are both of its backends, `MBEDTLS_THREADING_PTHREAD` (:2196) and `MBEDTLS_THREADING_ALT` (:2185). That one config knob cascades through everything:

- `mbedtls_threading_mutex_t` (the mutex type itself) only exists under `#if defined(MBEDTLS_THREADING_PTHREAD)` or `MBEDTLS_THREADING_ALT` (`threading.h:27-44`) — off by default, so the type doesn't exist.
- The four function pointers (`mbedtls_mutex_init/free/lock/unlock`) and all five global mutex externs (`threading.h:105-161`) are inside `#if defined(MBEDTLS_THREADING_C)` — off by default, so none of them exist either.
- `library/threading.c`, the only file that implements lock/unlock, is itself wrapped in the same guard — it compiles to an empty translation unit by default.
- Every call site that would take a lock — in `rsa.c`, `ctr_drbg.c`, `entropy.c`, `hmac_drbg.c`, `memory_buffer_alloc.c`, `platform_util.c`, `psa_crypto*.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, `x509_crt.c` — is individually wrapped in `#if defined(MBEDTLS_THREADING_C)` (verified e.g. `rsa.c:1238-1259`). With the option off, these are plain, unsynchronized code paths.

The two "thread spawns" the index found aren't in the library at all — they're in optional sample/test programs (`programs/ssl/ssl_pthread_server.c`, `programs/test/benchmark.c`). The pthread server sample even checks for you: it opens with `#elif !defined(MBEDTLS_THREADING_C) || !defined(MBEDTLS_THREADING_PTHREAD)` and, under the default config, just prints "MBEDTLS_THREADING_PTHREAD not defined." and exits — it spawns nothing.

This matches the doc comment right above the option: *"Traditionally, Mbed TLS assumes it is used in a non-threaded environment or that contexts are not shared between threads."* Default mbedtls is a passive library: it creates no threads of its own, and it's on you (the caller) not to share a context across threads unless you turn threading on.

## If you enable `MBEDTLS_THREADING_C` (+ PTHREAD or ALT)

Since that's presumably the actual reason for asking, here's what the mutexes protect once you opt in — none of it exists otherwise:

| Mutex | Scope | Protects |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | global, PSA | `registered_readers`/`state` for every slot in the PSA key-slot table |
| `mbedtls_threading_psa_globaldata_mutex` | global, PSA | rest of the PSA `global_data` struct (implicit shared state every `psa_xxx()` call touches) |
| `mbedtls_threading_psa_rngdata_mutex` | global, PSA | PSA's global RNG state |
| `mbedtls_threading_readdir_mutex` | global | non-reentrant `readdir()` inside `mbedtls_x509_crt_parse_path` (`x509_crt.c`) |
| `mbedtls_threading_gmtime_mutex` | global | non-reentrant libc `gmtime()` fallback in `mbedtls_platform_gmtime_r` (`platform_util.c`) |
| `ctx->mutex` in `mbedtls_rsa_context` | per-context | serializes concurrent ops (e.g. blinding value regen) on **one shared** RSA context |
| `ctx->mutex` in `mbedtls_ctr_drbg_context` / `mbedtls_entropy_context` | per-context | serializes reseed/generate calls if that DRBG/entropy context is shared across threads |
| mutexes in `ssl_cache.c`/`ssl_cookie.c`/`ssl_ticket.c` | per-context | shared server-side session cache / cookie / ticket state across worker threads |

Note the design intent: this protects **global/implicit state and explicitly-shared contexts**, not "every object automatically." A context used by exactly one thread gets no locking overhead and needs none — which is exactly why, with the option off (the default), you get zero synchronization cost, at the price of zero built-in thread-safety.
