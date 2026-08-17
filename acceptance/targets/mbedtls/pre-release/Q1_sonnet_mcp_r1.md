# Q1 — mcp — sonnet — run 1

Yes — mbedtls uses mutexes extensively, all built on a single pluggable abstraction layer rather than raw pthread calls scattered through the code.

## The abstraction: function-pointer indirection

`include/mbedtls/threading.h:29` defines `mbedtls_threading_mutex_t`, a struct wrapping a `pthread_mutex_t private_mutex` plus a `private_state` field used only by test instrumentation.

The actual lock/unlock/init/free operations are **global function pointers**, not direct calls:
- `mbedtls_mutex_init`, `mbedtls_mutex_lock`, `mbedtls_mutex_unlock` are declared `extern` in `include/mbedtls/threading.h:111-114` and defined as function-pointer variables in `library/threading.c:101-104`.
- By default they're initialized to the pthread-backed implementations: `threading_mutex_init_pthread` (`library/threading.c:51-64`, wraps `pthread_mutex_init`) and `threading_mutex_lock_pthread` (`library/threading.c:75-86`, wraps `pthread_mutex_lock`).
- `mbedtls_threading_set_alt()` (`library/threading.c:133-154`) lets an application swap in its own mutex implementation (e.g. for a non-pthread OS/RTOS) by overwriting these four pointers, then re-initializes the library's own static mutexes through the new pointers.

All of this is gated behind `MBEDTLS_THREADING_C` / `MBEDTLS_THREADING_PTHREAD` (`library/threading.c:18,50`) — locking is compiled out entirely if threading support isn't enabled.

## Where mutexes are used

Ten distinct lock identities exist in the codebase, all first-party:

**Global/static mutexes** (declared once, protecting module-level state), all `mbedtls_threading_mutex_t`, initialized via the function pointers above:
- `mbedtls_threading_key_slot_mutex` — protects the PSA key-slot table. Acquired around key lifecycle operations: `psa_destroy_key` (`library/psa_crypto.c:1310-1421`), `psa_start_key_creation`/`psa_finish_key_creation`/`psa_fail_key_creation` (`library/psa_crypto.c:1801-1808, 1927-1991, 2022-2045`), and `psa_get_and_lock_key_slot`/`psa_close_key`/`psa_purge_key`/`psa_unregister_read_under_mutex` in `library/psa_crypto_slot_management.c:822-891, 938-943, 1034-1055, 1071-1090`.
- `mbedtls_threading_psa_globaldata_mutex` — protects PSA global init state, e.g. `psa_get_initialized`/`psa_get_drivers_initialized` (`library/psa_crypto.c:141-148, 159-165`), `mbedtls_psa_crypto_free`/`mbedtls_psa_crypto_init_subsystem` (`library/psa_crypto.c:8407-8593`).
- `mbedtls_threading_psa_rngdata_mutex` — protects the shared PSA RNG/DRBG state, e.g. `psa_random_reseed`/`psa_random_deplete` (`library/psa_crypto.c:8030-8056`), `mbedtls_psa_crypto_init_subsystem` (`library/psa_crypto.c:8545-8560`), `psa_random_internal_generate` (`library/psa_crypto_random.c:147-154`).
- `mbedtls_threading_gmtime_mutex` — guards a non-reentrant `gmtime()` call (`library/platform_util.c`, 1 acquisition).
- `mbedtls_threading_readdir_mutex` — guards non-reentrant `readdir()` use in certificate-path loading (`library/x509_crt.c`, 1 acquisition).

**Per-object mutexes** (embedded as a struct member, one instance per object):
- `mbedtls_rsa_context.private_mutex` (`include/mbedtls/rsa.h:120`) — serializes access to a single RSA context (e.g. blinding-value state) across calls like `mbedtls_rsa_private`/`mbedtls_rsa_public`. Locked/unlocked via `mbedtls_mutex_lock/unlock(&ctx->mutex)` at `library/rsa.c:1239,1257,1518,1631`.
- `cache->mutex` in the SSL session cache (`library/ssl_cache.c`) — protects `mbedtls_ssl_cache_get/set/remove`.
- `heap.mutex` in `library/memory_buffer_alloc.c` — protects the static heap used by `mbedtls_memory_buffer_alloc_init` when `MBEDTLS_THREADING_C` is on, so the allocator is thread-safe.
- `debug_mutex` in `programs/ssl/ssl_pthread_server.c` — an example-program-level mutex serializing debug-log output across the demo's worker threads (`handle_ssl_connection`, spawned via `pthread_create` at `programs/ssl/ssl_pthread_server.c:277`).

## How the locking works, mechanically

Every use follows the same pattern: `mbedtls_mutex_lock(&mutex)` → check return code → critical section → `mbedtls_mutex_unlock(&mutex)` → check return code (both calls return `int`, propagating `MBEDTLS_ERR_THREADING_MUTEX_ERROR`/`MBEDTLS_ERR_THREADING_BAD_INPUT_DATA` on failure rather than asserting). Locks are exclusive (no reader/writer distinction) and all critical sections found are single-mutex — the index found **zero two-lock nestings**, i.e. no traced critical section here calls into a function that itself takes a second mutex, so there's no cross-mutex ordering to reason about from what's indexed.

## Gaps

- The index reports lock **identities** by operand spelling, not by distinct runtime object — for the per-object mutexes (`ctx->mutex`, `cache->mutex`, `heap.mutex`, `mutex->mutex`), I confirmed line numbers for `ctx->mutex` in `library/rsa.c` via a direct grep (the index's own `dossier` can't resolve a bare member-expression name to a site list — expected per its documented limitation). I did not similarly re-verify exact line numbers for `cache->mutex` and `heap.mutex`; their file locations came from the index's `search(corpus=locks)` result, not a line-numbered site.
- I did not check whether any lock/unlock call sites exist elsewhere that use a different spelling of the same mutex operand (the index's own caveat: an identity is `(name, scope, kind)`, so a second spelling of the same object would appear as a separate, uncounted row).
- Nesting analysis (0 two-lock holdings) only covers call-graph-traceable nesting inside indexed functions; it is not a deadlock proof and doesn't account for locking done through unresolved/fnptr-indirect calls the index marks `ambiguous`.
