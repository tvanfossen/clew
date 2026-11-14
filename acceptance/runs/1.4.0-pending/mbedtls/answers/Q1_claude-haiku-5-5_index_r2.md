## Short answer

In the default configuration, the library runs nothing concurrently and protects nothing. Every mutex in the library is compiled out. Any concurrency comes from the application that links it.

## Why: the default config turns threading off

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, so the threading layer is off.
- `mbedtls_config.h:2185` (`MBEDTLS_THREADING_ALT`) and `:2196` (`MBEDTLS_THREADING_PTHREAD`) are also commented out.
- Every mutex use is wrapped in `#if defined(MBEDTLS_THREADING_C)`. Examples: `ssl_cache.c:83` and `ssl_cache.c:104`, the mutex field in `ssl_cache.h:71`, and the top-level gate in `threading.c:18`.

**The index's configuration is not the default.** The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` passed as flags, so the mutex code it reports is the non-default variant. The index also has no config header recorded, so it cannot answer what the repo enables by default. I took the default from the header directly.

## What runs concurrently

**Library code: no threads.** The index finds 4 thread spawns in this repository, and all of them are in `programs/`:

| Spawn site | What it is | Needs |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | `handle_ssl_connection` per accepted client | THREADING_C + PTHREAD |
| `programs/test/benchmark.c:430,444` | `TimerProc` and `sighandler` for alarms | Test tool |
| `programs/ssl/ssl_server2.c:1699` | `term_handler` on SIGTERM/SIGINT | Test tool |

`ssl_pthread_server.c:24-27` refuses to build unless both THREADING_C and THREADING_PTHREAD are defined. So the only real multi-threaded program needs non-default settings.

**Signal handler caveat.** `ssl_server2.c:1069-1074` sets a plain `static int received_sigterm` from a signal handler and closes the listen and client fds. That is not `sig_atomic_t`, and nothing protects it. It is test-tool code, so the risk is limited, but it is not a model to copy.

## What protects what, if THREADING_C + PTHREAD are enabled

The mutex type is `mbedtls_threading_mutex_t`. The lock/unlock/init/free calls are function pointers (`threading.c:101-104`) that default to pthread, and `mbedtls_threading_set_alt` (`threading.c:133`) swaps them. It writes globals with no locking, so it must run before any thread starts.

| Scope | Object | Guards | Evidence |
|---|---|---|---|
| Per context | `ssl_cache` | Entry lookup, copy and store in get/set/remove | `ssl_cache.c:83-107`, `:259`, `:331` |
| Per context | `ssl_ticket` | Ticket key state | `ssl_ticket.c:330`, `:445` |
| Per context | `ctr_drbg`, `hmac_drbg` | DRBG state during generate and reseed | `ctr_drbg.c:703`, `hmac_drbg.c:388` |
| Per context | `rsa` | Lock sites at `rsa.c:1239` and `:1518` | I did not read the bodies, so I can't say which state they cover |
| Process global | `memory_buffer_alloc` heap | The whole heap, on alloc and free | `memory_buffer_alloc.c:544-562` |
| Process global | PSA global data, key-slot table, RNG data | Key-slot state and readers, RNG state | `psa_crypto.c:131-165`, `:2022`; `psa_crypto_core.h:106-113` |
| Process global | `gmtime_r` fallback, `readdir` | Shared static buffers | `platform_util.c:189`; `threading.c:101-104` |

The PSA slot protocol is the subtle part. A reader registers under the key-slot mutex, and `psa_key_slot_has_readers` must be called holding the global key-slot mutex (`psa_crypto_core.h:186-188`).

**Not protected by the library.** The index shows no mutex on `mbedtls_ssl_context` or on most caller-owned objects. An SSL connection is therefore single-owner, and the caller must not share one across threads. This is inferred from the absence of a lock on the type, not from a direct check of every path.

## Hazards in the default build

- **Two threads on one default build share unprotected state.** This covers PSA global state, the entropy and DRBG contexts, and the heap. The mutexes that would protect them are compiled out.
- **`MBEDTLS_SSL_CACHE_C` is on by default** (`mbedtls_config.h:3670`) but unlocked when threading is off. A server that shares a session cache across threads gets no protection. The code comments on `ssl_cache.h:85`, `:106`, and `:124` say the cache is thread-safe only if THREADING_C is enabled.
- **The index's `lock` layer lists one identity** (`mutex->mutex` in `threading.c`). It cannot model member mutexes such as `ctx->mutex`, so that count is not a mutex count.

## Verification gaps

- I confirmed the gating for `ssl_cache.c`, `threading.c`, `psa_crypto_core.h`, and the header defaults by reading them. For the other lock sites (entropy, DRBGs, RSA, ticket, heap, PSA), I went by the index's gate listing and the grep output. I did not open every site.
- I did not run a build, so the claim that a default build compiles with every mutex removed is from source reading, not a compile test.