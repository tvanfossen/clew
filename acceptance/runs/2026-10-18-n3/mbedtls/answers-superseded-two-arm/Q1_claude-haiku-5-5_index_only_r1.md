**Short answer:** As far as the index can tell, the library itself runs no concurrent code and takes no locks in its default configuration. The index cannot confirm the default directly, so treat this as an inference (see the caveat).

**Caveat: the index is not the default build.** It was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` forced on by flag, and no `config_header` is recorded, so the repository's own default is not in the index. The evidence points to threading being off by default: `MBEDTLS_THREADING_C` gates about 100 files but has no `#define` site anywhere in the index, while `MBEDTLS_HAVE_TIME` and `MBEDTLS_PSA_CRYPTO_C` do have definitions in `include/mbedtls/mbedtls_config.h`. The index's own note says a missing definition usually means it is commented out. Declaring `preprocessor.config_header` would settle it.

**What runs concurrently.** The index has four spawn sites, all in `programs/`. None are in `library/`.

| Thread or handler | Location | Gate | What it does |
|---|---|---|---|
| `handle_ssl_connection` (pthread) | `programs/ssl/ssl_pthread_server.c:277` | `MBEDTLS_THREADING_PTHREAD` | One thread per client connection, with its own SSL context. All threads share the config handle. |
| `TimerProc` (Win32 thread) | `programs/test/benchmark.c:430` | `_WIN32` | Alarm thread that sets `mbedtls_timing_alarmed`. |
| `sighandler` (signal) | `programs/test/benchmark.c:444` | POSIX path | Sets `mbedtls_timing_alarmed`. |
| `term_handler` (signal) | `programs/ssl/ssl_server2.c:1699` | POSIX path | Sets `received_sigterm` and closes the listen and client fds. |

The pthread server only compiles with threading enabled, so in the default build it does not exist.

**What protects what.** The global mutexes are declared in `include/mbedtls/threading.h` and defined in `library/threading.c:182-190`.

| Lock | What the index shows |
|---|---|
| `mbedtls_threading_key_slot_mutex` | Taken by `psa_unregister_read_under_mutex` (`psa_crypto_slot_management.c:931`) around `psa_unregister_read`. This is the only global-mutex acquisition in a function body that the index shows. |
| `heap.mutex` (`memory_buffer_alloc.c`) | Wraps `buffer_alloc_calloc` and `buffer_alloc_free` via `buffer_alloc_calloc_mutexed` (line 541). It serializes the buffer heap. |
| `mbedtls_threading_readdir_mutex`, `…gmtime_mutex`, `…psa_globaldata_mutex`, `…psa_rngdata_mutex` | Declared and defined, but the index shows no acquisition site. I cannot say whether they are used. |

Beyond those, the code calls `mbedtls_mutex_lock` through a function pointer from entropy, CTR-DRBG, HMAC-DRBG, RSA, the SSL cache, cookie and ticket code, x509 path parsing, and PSA key and RNG functions. The index shows those callers but not which object each mutex lives in. The lock layer lists a single identity, `mutex->mutex`, with scope unknown and low confidence. Any claim that a given lock protects a given field, such as the entropy pool or the session cache, is an inference from function names.

Two more facts from the index:
- The pthread backend is the default. `mbedtls_mutex_lock` and its siblings are function pointers that default to the pthread implementation (`library/threading.c:103`). The index also shows `MBEDTLS_THREADING_ALT` and `MBEDTLS_THREADING_IMPL` gates, so the backend can be replaced.
- The index reports zero two-lock nestings. That is not a proof of deadlock freedom.

**Practical reading.** In the default build, there are no library-internal locks. An application that shares an SSL context, PSA key slot, or RNG across threads has to serialize access itself. If you enable `MBEDTLS_THREADING_C`, the locks above apply, with the gaps noted.