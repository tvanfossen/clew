## What actually runs concurrently

Two independent things exist in this repo under the "threading" heading, and neither one is "the library spawning threads":

**1. The library itself never spawns a thread.** The thread-spawn scan (`clew` search over `ast_spawn` sites) found exactly two threads in the whole tree, and both are in `programs/`, not `library/`:
- `programs/ssl/ssl_pthread_server.c:277` (`thread_create` → `handle_ssl_connection`) — the example pthread SSL server spawns one worker thread per accepted connection.
- `programs/test/benchmark.c:430` (`mbedtls_set_alarm` → a Win32 `TimerProc`) — a benchmark timer callback, not really "concurrency" in the mutex sense.

So concurrency is something an *application embedding mbedtls* creates by calling the library from multiple threads it manages itself (the pthread example program is a demonstration of exactly that pattern) — mbedtls doesn't do it for you.

**2. Mutex protection is compiled out by default.** `MBEDTLS_THREADING_C` gates ~140 call sites across the library (bignum, rsa, ctr_drbg, entropy, hmac_drbg, memory_buffer_alloc, psa_crypto*, ssl_cache, ssl_cookie, ssl_ticket, x509_crt, platform_util, debug, error), but the index shows **no definition site at all** for `MBEDTLS_THREADING_C` in `include/mbedtls/mbedtls_config.h` — meaning it is commented out in the shipped config, unlike e.g. `MBEDTLS_PSA_CRYPTO_C`, which does have a live `#define` at `mbedtls_config.h:3334`. So as shipped: `mbedtls_mutex_lock/unlock/init/free` in `include/mbedtls/threading.h` are function pointers, `library/threading.c` wires them to `threading_mutex_dummy` (a no-op — the body is literally `((void) mutex); return;`) rather than to the pthread implementations (`threading_mutex_lock_pthread` etc., also present in `threading.c` but only compiled in under `MBEDTLS_THREADING_PTHREAD`). Every `mbedtls_mutex_lock(...)`/`mbedtls_mutex_unlock(...)` call site in the library still executes, it just does nothing — no actual mutual exclusion happens.

## What protects what (when threading support *is* enabled)

If an application turns on `MBEDTLS_THREADING_C` (+ `MBEDTLS_THREADING_PTHREAD`, or supplies its own via `mbedtls_threading_set_alt`), the index shows these distinct locks, each protecting a specific piece of state:

| Mutex | Scope | Protects |
|---|---|---|
| `mbedtls_threading_gmtime_mutex` (global, gated `THREADING_USE_GMTIME`) | process-wide | the non-reentrant libc `gmtime()` call |
| `mbedtls_threading_readdir_mutex` (global, gated `MBEDTLS_FS_IO`) | process-wide | the non-reentrant `readdir()` call |
| `mbedtls_threading_key_slot_mutex` (global, gated `MBEDTLS_PSA_CRYPTO_C`) | process-wide | PSA key-slot table state (e.g. `psa_unregister_read_under_mutex`) |
| `mbedtls_threading_psa_globaldata_mutex` / `mbedtls_threading_psa_rngdata_mutex` (global) | process-wide | PSA global crypto state / PSA's global RNG state |
| `cache->mutex` (per-`mbedtls_ssl_cache_context`) | per SSL cache object | `mbedtls_ssl_cache_get`/`mbedtls_ssl_cache_set` — the session cache lookup/insert |
| `ctx->mutex` (per-`mbedtls_ssl_ticket_context`) | per ticket-context object | `mbedtls_ssl_ticket_write` (and presumably parse) — ticket key state during encrypt/decrypt |
| `heap.mutex` (per static heap in `memory_buffer_alloc.c`) | the buffer-allocator's static heap | `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` — the custom allocator's free list |

All of these are initialized either via the `MUTEX_INIT` macro at static-init time (for the global ones) or explicitly by `mbedtls_threading_set_alt` when an alternate mutex implementation is registered — that function's body shows it re-initializing `readdir_mutex`, `gmtime_mutex`, and the three PSA mutexes right after installing the new function pointers.

The `locks` corpus in the index only surfaced one *identity* row (`mutex->mutex` in `threading.c`, low confidence) — that's a generic dispatch/plumbing reference, not a count of real critical sections; the per-object list above (from following the actual call sites) is the real answer, and there are no reported "two-lock" nestings, so nothing in this set risks a lock-ordering deadlock as modeled.

## Bottom line

As configured out of the box, nothing in the mbedtls library runs concurrently on its own, and none of its internal mutex machinery is live — it's all no-ops. Concurrency and its protection only materialize if the embedding application (a) spawns its own threads calling into the library, exactly as `ssl_pthread_server.c` demonstrates, and (b) turns on `MBEDTLS_THREADING_C` (plus a pthread or ALT backend), at which point the mutexes above start actually protecting the SSL session cache, ticket keys, PSA key-slot/global/RNG state, the custom heap allocator, and the two non-reentrant libc calls.

One honest gap: I'm reading "no definition site" as "commented out by default" per the index's own documented convention for that field — I did not read `mbedtls_config.h` directly (no file-read tool available here), so I can't rule out some other reason a row would be absent; the call-site and structural picture above, though, comes straight from the graph and isn't in question.
