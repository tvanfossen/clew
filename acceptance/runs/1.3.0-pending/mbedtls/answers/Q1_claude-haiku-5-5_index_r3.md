**Short answer:** in the default configuration the library runs no threads and takes no locks. Nothing inside mbedtls runs concurrently with anything else. Concurrency exists only in the test and example programs, and those are unprotected by the library.

**Why the default is single-threaded**

The default config turns off every threading option:

| Macro | Default | Where |
|---|---|---|
| `MBEDTLS_THREADING_C` | off (commented out) | `include/mbedtls/mbedtls_config.h:3787` |
| `MBEDTLS_THREADING_PTHREAD` | off (commented out) | `mbedtls_config.h:2196` |
| `MBEDTLS_THREADING_ALT` | off (commented out) | `mbedtls_config.h:2185` |

With `MBEDTLS_THREADING_C` off, `library/threading.c` compiles to nothing, and every mutex use in the library is compiled out. The sampled guards confirm this: `memory_buffer_alloc.c:540` (the heap mutex wrapper), `psa_crypto.c:130` and the other PSA lock sites. I did not open every call site's guard, so the claim for the others (`ssl_cache.c`, `rsa.c`, `hmac_drbg.c`, `ssl_ticket.c`, `x509_crt.c`) rests on the pattern, not a per-site check.

The header's own documentation says the same thing: the library "assumes it is used in a non-threaded environment or that contexts are not shared between threads," and the PSA subsystem "has an implicit shared context," so any multithreaded use must enable `MBEDTLS_THREADING_C`.

**What runs concurrently in the repo**

The index finds four thread or signal spawn sites, all in `programs/`, none in `library/`:

- `programs/ssl/ssl_pthread_server.c:277` spawns a pthread per connection (`handle_ssl_connection`).
- `programs/test/benchmark.c:430` has a Win32 `TimerProc` and `:444` a `sighandler`, both via `mbedtls_set_alarm`.
- `programs/ssl/ssl_server2.c:1699` installs `term_handler` as a signal handler.

The signal handlers are asynchronous, so they can interrupt the library at any point. Nothing in the default build protects against that.

**What the mutexes protect when enabled**

These apply only when `MBEDTLS_THREADING_C` is on, and the pthread backend is selected.

| Mutex (`include/mbedtls/threading.h`) | Protects | Evidence |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key-slot table, registered readers | `psa_crypto.c:1310–2045`, `psa_crypto_slot_management.c:822` |
| `mbedtls_threading_psa_globaldata_mutex` | Non-RNG PSA `global_data` fields | `psa_crypto.c:141–166`, `:8407–8594`; `slot_management.c:200` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state and `rng_state` | `psa_crypto.c:131`, `:8030–8425` |
| `mbedtls_threading_readdir_mutex` | Non-reentrant `readdir()` in CRT directory parsing | `x509_crt.c:1611` and `:1660` |
| `mbedtls_threading_gmtime_mutex` | `gmtime()` fallback, only where no thread-safe variant exists | `threading.c` (`THREADING_USE_GMTIME`) |
| `ctx->mutex` / `cache->mutex` (per object) | Session cache, ticket keys, RSA context, HMAC-DRBG state | `ssl_cache.c:84,259,331`, `ssl_ticket.c:330,445`, `rsa.c:1239,1518`, `hmac_drbg.c:388` |
| `heap.mutex` | Heap allocator in `memory_buffer_alloc.c` | `:544`, `:558` |

Per-object locks protect only the object they live in. Application data passed between threads, or TLS, X.509 and PK contexts shared between threads, get no protection from them.

**Caveats on the index**

- The lock layer reports one identity, `mutex->mutex` in `threading.c`, at low confidence, because member expressions are not modelled. The named globals above come from the symbol inventory and the source, not from the lock layer.
- The lock layer also reports zero nested two-lock holdings. That is a database result, not a proof of deadlock freedom.
- The thread layer counts only spawn primitives this build's patterns match (pthread, Win32, signals). Other spawn mechanisms would be missed silently.