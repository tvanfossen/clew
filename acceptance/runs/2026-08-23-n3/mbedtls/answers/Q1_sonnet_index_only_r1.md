This confirms the shape well enough to answer directly from what the index actually shows, with one honest gap flagged.

## What actually runs concurrently

The index finds exactly **two** first-party thread-spawn sites in this whole repository, and neither is in the library:

| Spawn site | Primitive | Entry | What it does |
|---|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` (`thread_create`) | pthread | `handle_ssl_connection` | demo TLS server spawns one thread per accepted connection |
| `programs/test/benchmark.c:430` (`mbedtls_set_alarm`) | Win32 timer | `TimerProc` | benchmark program's alarm callback |

**`library/*.c` itself spawns nothing.** mbedtls is not a multithreaded library — it is a library that is *safe to call from* multiple threads (to varying degrees, see below) provided the *application* creates the threads. The only concurrency in this repo's own source is in an example server and a benchmark harness, not the TLS/crypto core.

## What protects what

`library/threading.c` + `include/mbedtls/threading.h` define one abstract type, `mbedtls_threading_mutex_t`, and four global function pointers the rest of the library calls indirectly: `mbedtls_mutex_init/free/lock/unlock`. What those pointers resolve to is config-gated:

- **`MBEDTLS_THREADING_PTHREAD`** → they resolve to `threading_mutex_{init,free,lock,unlock}_pthread`, which wrap a real `pthread_mutex_t` member (`mutex->mutex`) — confirmed body: `threading_mutex_lock_pthread` calls `pthread_mutex_lock(&mutex->mutex)`.
- **`MBEDTLS_THREADING_ALT`** → the application supplies its own implementation via `mbedtls_threading_set_alt`; the index has no definition site for that hook, which is expected (it's a runtime-registered callback, not compiled-in code).
- **Neither defined** → `threading.c` still compiles the fallback pair `threading_mutex_dummy` (init/free/unlock — literal no-ops) and `threading_mutex_fail` (lock — always returns `MBEDTLS_ERR_THREADING_BAD_INPUT_DATA`).

**Gap I can't close from the index:** whether `MBEDTLS_THREADING_C` is itself on in mbedtls's shipped default config is not answerable here — no `config_header` is declared for this target, so `mbedtls_config.h`'s actual default is outside what I can query. This build's `configured_macros` shows `MBEDTLS_THREADING_C`/`MBEDTLS_THREADING_PTHREAD` as *operator-supplied preprocessor flags for indexing*, explicitly not evidence of the repo's shipped default (the tool says so directly). What the index *can* tell you is the fallback exists and one of its four functions is fail-closed on lock — that's a structural fact about the code, not a statement about which branch ships active.

Given that, what's actually guarded (once locking is live) breaks into two shapes:

**Five global, library-wide mutexes** (`library/threading.c`, all `static ... MUTEX_INIT`):
- `mbedtls_threading_gmtime_mutex` — serializes calls into non-reentrant libc `gmtime` from `mbedtls_platform_gmtime_r`.
- `mbedtls_threading_readdir_mutex` — serializes `readdir()` inside `mbedtls_x509_crt_parse_path` when loading a cert directory.
- `mbedtls_threading_key_slot_mutex` — guards PSA key-slot bookkeeping (`psa_get_and_lock_key_slot`, `psa_close_key`, `psa_destroy_key`, `psa_purge_key`, key-creation/finish/fail paths).
- `mbedtls_threading_psa_globaldata_mutex` — guards PSA's global init flags (`psa_get_initialized`, `psa_get_drivers_initialized`, `psa_get_key_slots_initialized`).
- `mbedtls_threading_psa_rngdata_mutex` — guards PSA's global RNG state (`psa_random_deplete/reseed/generate/set_prediction_resistance`).

**Per-context mutexes embedded as struct members**, each protecting only its own object's shared state, so concurrent use of *different* contexts never contends:
- `mbedtls_rsa_context.mutex` — protects RSA blinding state during `mbedtls_rsa_private`/`mbedtls_rsa_public`.
- `mbedtls_ssl_cache_context.mutex` — protects the SSL session cache chain shared across connections/threads.
- `mbedtls_ssl_cookie_ctx.mutex` — protects the DTLS cookie HMAC context/serial counter.
- `mbedtls_ssl_ticket_context.mutex` — protects the session-ticket key material.

Also `library/memory_buffer_alloc.c` wraps its static-buffer allocator's calloc/free (`buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed`) in the same lock/unlock pointers when `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is also enabled.

One caveat on the index itself: the `locks` corpus collapses **all** of this to a single reported lock identity, `mutex->mutex` — every one of the objects above is a `mbedtls_threading_mutex_t` accessed through the same generic pthread wrapper, so the layer that counts distinct lock identities by call-site spelling can't tell the RSA context's mutex from the SSL cache's from the global gmtime mutex; it explicitly says to `dossier` the owning type to enumerate them, which is what the struct lookups above did.
