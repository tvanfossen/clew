## Short answer

In the default configuration, the library runs no concurrency of its own and takes no locks. Any concurrency comes from the application calling it. The mutexes only exist when `MBEDTLS_THREADING_C` is enabled, and then they protect a small set of library globals plus the heap.

## Default configuration

- `MBEDTLS_THREADING_C` defaults to off (`include/mbedtls/mbedtls_config.h:3787`).
- `MBEDTLS_THREADING_PTHREAD` defaults to off (`include/mbedtls/mbedtls_config.h:2196`).
- With both off, `library/threading.c` (gated at lines 18–193) compiles to nothing, and the heap wrappers in `memory_buffer_alloc.c:540–564` are not compiled in.
- The four thread spawn sites the index found are all in `programs/`, not `library/`:

| Thread | Spawn site | Gate / platform |
|---|---|---|
| `handle_ssl_connection` (pthread) | `programs/ssl/ssl_pthread_server.c:277` | `MBEDTLS_THREADING_PTHREAD` |
| `TimerProc` (Win32) | `programs/test/benchmark.c:430` | Windows timing alarm |
| `sighandler` (ISR) | `programs/test/benchmark.c:444` via `mbedtls_set_alarm` | timing alarm |
| `term_handler` (ISR) | `programs/ssl/ssl_server2.c:1699` | signal handler |

The library spawns nothing, so under default settings it runs on whatever threads the caller provides.

## When threading is enabled

**Caveat:** the index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set by the operator, so the lock and thread rows below describe a threaded build, not the shipped default.

What runs concurrently:
- Application threads (in the test server, one pthread per client connection, `ssl_pthread_server.c:277`) each drive their own `mbedtls_ssl_context` through handshake and I/O. The handler reaches about 1,094 functions, so it touches most of the library.
- Shared library state is touched from those threads at the same time.

What the mutexes protect, per the index:

| Lock | Declared | Protects / used by |
|---|---|---|
| `mbedtls_threading_key_slot_mutex` | `threading.c:188` | PSA key slots. `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) holds it around `psa_unregister_read`. Its callers include most `psa_*` entry points in `psa_crypto.c`. |
| `mbedtls_threading_psa_globaldata_mutex` | `threading.c:189` | PSA global data. Declared; I did not confirm which functions take it. |
| `mbedtls_threading_psa_rngdata_mutex` | `threading.c:190` | PSA RNG data. Declared; users not confirmed. |
| `mbedtls_threading_gmtime_mutex` | `threading.c:185` | Serialises `gmtime`-style calls. Users not confirmed. |
| `mbedtls_threading_readdir_mutex` | `threading.c:182` | Serialises `readdir`-style calls. Users not confirmed. |
| `heap.mutex` | `memory_buffer_alloc.c` (`buffer_alloc_calloc_mutexed` 541, `buffer_alloc_free_mutexed` 554) | The buffer allocator's heap. |

The heap wrapper has an explicit policy: on a free-path lock failure it leaks rather than touch the heap, because "corrupting the heap seems worse than losing memory" (`memory_buffer_alloc.c:554–563`).

The lock on `mutex->mutex` in `threading_mutex_lock_pthread` (`threading.c:81`) is the only lock identity the layer records, and it is the pthread wrapper itself, not any of the globals above.

## What is not protected

- **Per-connection objects.** The index shows no lock on `mbedtls_ssl_context` or other per-connection state. Sharing one context between threads is the caller's responsibility.
- **`mbedtls_timing_alarmed`.** `mbedtls_set_alarm` writes it from the test harness, and the alarm/signal paths run asynchronously. It is not under any mutex I could see. I did not inspect `TimerProc` or `term_handler` to confirm how the flag is set.

## Gaps in what the index can show

- The lock layer records only one identity (`mutex->mutex`). Acquisitions of the `mbedtls_threading_*` globals go through macros (`PSA_THREADING_CHK_RET(mbedtls_mutex_lock(&…))`) and are not modelled as locks. The "0 nestings" result therefore does not prove the absence of lock-order problems.
- Mapping the gmtime, readdir, and PSA globaldata/rngdata mutexes to their callers needs a source read. The index confirms their declarations only.