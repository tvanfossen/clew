**Short answer:** with the shipped defaults, nothing in the mbedtls library runs concurrently, and no mutex is taken. The threading code only compiles when `MBEDTLS_THREADING_C` is enabled. The concurrency that exists lives in the sample programs under `programs/`.

**Default configuration**

- `MBEDTLS_THREADING_C` defaults to off (`include/mbedtls/mbedtls_config.h:3787`). `MBEDTLS_THREADING_PTHREAD` also defaults to off (`mbedtls_config.h:2196`). Both are commented out, so the preprocessor sees no definition.
- The whole body of `library/threading.c` (lines 18–193) is gated by `MBEDTLS_THREADING_C`, so by default it contributes nothing.
- The index was built with both macros stated as flags. Its analysis therefore describes a threaded build, not the default. The "off by default" finding comes from the header's recorded default state, not from this build.

**Threads the index found (4 spawn sites, all in `programs/`)**

| Spawn site | What runs | Gate |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | One pthread per client connection, running `handle_ssl_connection` (`:98–244`) | `THREADING_C` and `THREADING_PTHREAD` |
| `programs/test/benchmark.c:430` | Win32 `TimerProc` | Windows only |
| `programs/test/benchmark.c:444` | `sighandler`, a signal handler that sets `mbedtls_timing_alarmed` | `MBEDTLS_HAVE_TIME`, `MBEDTLS_TIMING_ALT` off |
| `programs/ssl/ssl_server2.c:1699` | `term_handler`, a signal handler | — |

The library itself (`library/`) has no spawn sites. The thread detection is pattern-based, so a caller's own threads would not appear.

**What protects what, when threading is enabled**

- **Mutex abstraction:** `mbedtls_mutex_init/lock/unlock/free` are function pointers (`include/mbedtls/threading.h:105–161`), defaulting to the pthread implementation in `threading.c`. `MBEDTLS_THREADING_ALT` exists as a gate symbol, so a platform can substitute its own; I did not confirm the setter's name from the index.
- **Global library mutexes** (`threading.c:188–189`, initialized with `PTHREAD_MUTEX_INITIALIZER`, declared in `threading.h`):
  - `mbedtls_threading_key_slot_mutex` (`:144`), which by name guards PSA key slots
  - `mbedtls_threading_psa_globaldata_mutex` (`:151`)
  - `mbedtls_threading_psa_rngdata_mutex`
  - `mbedtls_threading_gmtime_mutex`
  - `mbedtls_threading_readdir_mutex`

  The index does not show their use sites. The lock layer recorded only one acquisition (`mutex->mutex` in `threading.c`), so these protections are inferred from the names and need a source read to confirm.
- **Heap:** `heap.mutex` in `library/memory_buffer_alloc.c` is the one lock whose protected data I can state. `buffer_alloc_calloc_mutexed` (`:541–552`) takes it around `buffer_alloc_calloc`, serializing the buffer allocator. It is gated by `THREADING_C` (`:540–564`).
- **Lock nesting:** the index reports zero two-lock holdings. That is a definitive empty result for this index, not a proof of deadlock freedom.

**In the sample server**

- Each connection thread has its own `mbedtls_ssl_context` and client socket, passed via `thread_info_t`. The `ssl_config` is shared across threads through `thread_info->config`.
- `debug_mutex` and `my_mutexed_debug` in `ssl_pthread_server.c` appear to serialize debug output; the name is the only evidence.
- `sighandler` writes `mbedtls_timing_alarmed` from signal context with no lock or atomic that I could see in its body. That is a plain data race and a signal-safety question in a test program, not in the library.