**Short answer: in the default configuration, the library runs no internal locks and creates no threads. Any concurrency is the caller's responsibility.**

**Why the default has no locking**

- `MBEDTLS_THREADING_C` defaults to off. The index reads the default from `include/mbedtls/mbedtls_config.h:3787`. Its gate covers `library/threading.c` (lines 18–193), and every mutex in the library sits behind that gate.
- `MBEDTLS_THREADING_PTHREAD` is also off by default (`mbedtls_config.h:2196`).
- Caveat: the index was built with both macros passed as flags (`configured_macros`). So the lock and thread layers I read describe that build, not the shipped default. The index also reports no definition site for `MBEDTLS_THREADING_C`, so the "off" reading likely comes from a commented-out `#define`. Confirm against the header.

**What runs concurrently**

| Context | Thread or signal | Gate | Under default config |
|---|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | `handle_ssl_connection`, one pthread per connection | whole file gated by `MBEDTLS_THREADING_C` (lines 24–492) | not built |
| `programs/test/benchmark.c:430,444` | `TimerProc` (Win32), `sighandler` (alarm) | not checked | test tool only |
| `programs/ssl/ssl_server2.c:1699` | `term_handler` signal handler | not checked | test tool only |

The only spawn in the index that touches shared state is the per-connection pthread server. It is a sample program, not library code. The library itself spawns nothing.

**What the mutexes protect, when threading is enabled**

The lock layer shows one acquisition: `threading_mutex_lock_pthread` at `library/threading.c:81`. The library reaches it through the `mbedtls_mutex_lock` function pointer, so its callers resolve as indirect calls. The index lists about 38 callers, including:

- **CTR_DRBG, HMAC_DRBG and entropy** (`ctr_drbg.c`, `hmac_drbg.c`, `entropy.c`): the shared RNG state.
- **SSL session cache, cookie and ticket** (`ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`): server-side session state.
- **PSA key slots** (`psa_crypto*.c`): global key-slot table.
- **Memory buffer allocator** (`memory_buffer_alloc.c`, `buffer_alloc_*_mutexed`): allocator state.
- **`gmtime` and `readdir`** (`platform_util.c`, `x509_crt.c`): non-reentrant libc calls.
- **Debug output** (`debug.c`, `my_mutexed_debug`): serialized logging.

The mutexes are global objects in `library/threading.c` with `MUTEX_INIT`:

- `mbedtls_threading_key_slot_mutex` (line 188): protects the key-slot table. The clearest case is `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931–947`), which locks around `psa_unregister_read` and is a no-op without threading.
- `mbedtls_threading_psa_globaldata_mutex` (line 189): PSA global data.
- `mbedtls_threading_psa_rngdata_mutex`, `mbedtls_threading_gmtime_mutex`, `mbedtls_threading_readdir_mutex`: RNG, `gmtime` and `readdir`.

The index does not record which call sites take the global-data, RNG, `gmtime` or `readdir` mutexes. Those are read through `mbedtls_mutex_lock(&…)`, which the lock layer does not model.

**What the index cannot settle**

- Whether the library has unguarded shared mutable state in the default build. The index has no shared-state layer that would answer this, so I can't confirm it either way.
- Whether a caller using one object from several threads is safe. Nothing in the index says the library promises that.