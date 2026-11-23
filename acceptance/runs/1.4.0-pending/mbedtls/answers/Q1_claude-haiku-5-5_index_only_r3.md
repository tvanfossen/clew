**Short answer:** with the default configuration the library runs no threads and takes no locks. Any concurrency comes from the application that calls it. The mutexes in the source only exist when `MBEDTLS_THREADING_C` is enabled, and the index says it is off by default.

**Default configuration**

- `MBEDTLS_THREADING_C` has `default_state: off`, declared at `include/mbedtls/mbedtls_config.h:3787`. Every mutex-using site is gated on it, including `memory_buffer_alloc.c:540`, `psa_crypto_slot_management.c:931`, and all of `library/threading.c` (lines 18–193).
- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` passed as flags, so its own variant is threaded. I took the default from the header, not from the build flags. No `config_header` is recorded for this target, so the index cannot confirm the shipped default beyond that line.
- With the gate off, `psa_unregister_read_under_mutex` is just `psa_unregister_read`, and `buffer_alloc_calloc_mutexed` is never compiled in.

**What runs concurrently (the first-party spawns)**

The index finds four thread or signal entry points, all in `programs/`. None are in `library/`.

| Spawn | Where | What it does | Shared state |
|---|---|---|---|
| `handle_ssl_connection` (pthread) | `programs/ssl/ssl_pthread_server.c:277` | One thread per accepted connection, running a full SSL handshake and I/O | Per-connection `ssl` context. Shared `config` and the program's own debug mutex. |
| `TimerProc` (Win32) and `sighandler` (signal) | `programs/test/benchmark.c:430,444` | Set `mbedtls_timing_alarmed = 1` after a delay | A plain flag, with no lock |
| `term_handler` (signal) | `programs/ssl/ssl_server2.c:1699` | Sets `received_sigterm` and calls `mbedtls_net_free` on the listen and client sockets | Plain globals, written from signal context |

Note the `ssl_pthread_server` thread is gated on `MBEDTLS_THREADING_C` (line 30). Without it, the example does not build with threads.

**What the mutexes protect when `MBEDTLS_THREADING_C` is on**

The mutexes are function pointers (`mbedtls_mutex_lock` and friends, `threading.c:103`) that default to pthread implementations. The index lists these globals in `threading.c` and `threading.h`:

- `mbedtls_threading_key_slot_mutex` protects PSA key-slot unregistration. `psa_unregister_read_under_mutex` takes it and is called from `psa_open_key` and from about 25 `psa_*` entry points in `psa_crypto.c`. This is the only lock whose callers I checked.
- `buffer_alloc_calloc_mutexed` wraps the memory buffer allocator's calloc and free with `heap.mutex`, serialising heap access.
- `mbedtls_threading_readdir_mutex` and `mbedtls_threading_gmtime_mutex` are declared, but I did not check their call sites.
- `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex` are declared, but I did not check their call sites.

**Limits of this index**

- The lock layer reports one acquisition, `mutex->mutex` in `threading.c`. The global mutexes are reached through function pointers, so the lock inventory is incomplete. The "0 nestings" result is not a proof of deadlock-freedom.
- The spawn count of 4 covers only the spawn primitives the index matched (`thread_create`, `mbedtls_set_alarm`, and signal handlers). It lists `thread_create` and `mbedtls_mutex_lock` as undeclared primitives, so a platform-specific spawn elsewhere would not appear.
- The library itself does not guard its own state against concurrent callers beyond these mutexes. Each `mbedtls_ssl_context` is used by one thread at a time in the example server, and nothing in the index shows the library protecting a shared context.