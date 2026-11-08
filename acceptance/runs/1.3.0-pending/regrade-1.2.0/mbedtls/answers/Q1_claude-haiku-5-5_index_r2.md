**Short answer:** With the default `mbedtls_config.h`, the library runs no threads and takes no locks. Any concurrency comes from the application calling into it. Mutexes exist only when `MBEDTLS_THREADING_C` is enabled, and even then they protect a small set of globals and per-context state.

**Default build**

- `MBEDTLS_THREADING_C` is commented out at `include/mbedtls/mbedtls_config.h:3787` (`//#define MBEDTLS_THREADING_C`). `MBEDTLS_THREADING_ALT` and `MBEDTLS_THREADING_PTHREAD` are also commented out (lines 2185, 2196).
- `library/threading.c` compiles to nothing without that macro. Every mutex use in the library is inside an `#if defined(MBEDTLS_THREADING_C)` block, so none of them is compiled in.
- The four thread-spawn sites the index finds are all in `programs/` (`ssl_pthread_server.c:277`, `benchmark.c:430/444`, `ssl_server2.c:1699`). The library spawns nothing.
- Unprotected shared state exists by default. The PSA subsystem keeps implicit global state: `global_data` and the key-slot table in `psa_crypto_slot_management.c`, and the RNG context in `psa_crypto_random.c`. The config's own doc comment says PSA "has an implicit shared context" and requires `MBEDTLS_THREADING_C` if more than one thread calls PSA. So PSA calls from multiple threads in a default build are data races. The fork-reseed path in `psa_crypto_random.c:146` (`pid != rng->pid`) is also unlocked.
- Per-context state is also unlocked by default. `ssl_cache.h:72`, `ssl_ticket.h:82`, `rsa.h:120` and `memory_buffer_alloc.c:63` carry mutex fields only under the same macro. Sharing a context between threads is the application's problem.

**With `MBEDTLS_THREADING_C` + `MBEDTLS_THREADING_PTHREAD`**

| Mutex (`threading.h`) | Protects | Where it is taken |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | PSA key-slot table | `psa_crypto_slot_management.c` (about 15 sites, e.g. 823–1091), `psa_crypto.c` 1311–2045, `psa_unregister_read_under_mutex` (931) |
| `mbedtls_threading_psa_globaldata_mutex` | `global_data`, `key_slots_initialized` | `psa_crypto_slot_management.c:200`, `psa_crypto.c` init/free paths (141–165, 8407–8594) |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state | `psa_crypto_random.c:147` (fork reseed), `psa_crypto.c` 8030–8561 |
| `mbedtls_threading_readdir_mutex` | non-reentrant `readdir` | `x509_crt.c:1611/1660` (directory loading), only with `MBEDTLS_FS_IO` |
| `mbedtls_threading_gmtime_mutex` | non-reentrant `gmtime` | `platform_util.c:189`, only on the fallback path where `gmtime_r` is unavailable |
| `heap.mutex` (per heap) | allocator state | `memory_buffer_alloc.c:541` `calloc_mutexed`/free wrappers |
| per-context mutexes | one SSL cache, ticket context, or RSA context | `ssl_cache.c`, `ssl_ticket.c`, `rsa.c` (blinding) |

Per-context mutexes protect only that context. They do not make two threads using the same TLS session safe.

**Caveats**

- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set as flags (`configured_macros`), so its gate data reflects that build. The default-off state comes from reading the header directly, and the index also reports `default_state: off` for the macro.
- The index's lock layer sees one identity (`mutex->mutex` in `threading.c`) and no nested holdings. It does not model the global mutexes above, so the table comes from grep and reading source, not from the lock corpus.
- With `MBEDTLS_THREADING_ALT`, the globals are initialised only inside `mbedtls_threading_set_alt()`. Until that runs, the default ALT callbacks are dummies (`threading_mutex_dummy`) or failures (`threading_mutex_fail`). Locking would then error, or silently not lock. I did not trace that path further.