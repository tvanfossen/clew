**Short answer:** with the default configuration, mbedtls runs no concurrency of its own and protects nothing internally. Its mutexes exist only when `MBEDTLS_THREADING_C` is enabled, and the threads in the repo are in `programs/`, not the library.

**Default build**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C` commented out. `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also commented out.
- `library/threading.c` is wrapped in `#if defined(MBEDTLS_THREADING_C)` (lines 18–193), so it compiles to nothing.
- Every mutex call site I checked sits behind the same guard: `ctr_drbg.c`, `entropy.c`, `hmac_drbg.c`, `memory_buffer_alloc.c`, `platform_util.c`, and `psa_crypto.c`.
- No thread is spawned from `library/`. The four spawn sites the index found are all in `programs/`: `ssl/ssl_pthread_server.c:277`, `test/benchmark.c` (the alarm `TimerProc` and `sighandler`), and `ssl/ssl_server2.c:1699` (`term_handler`).
- `ssl_pthread_server.c` builds to a stub `main` that prints "MBEDTLS_THREADING_PTHREAD not defined" and exits when threading is off (lines 24–29).
- The only process-wide side effect in the library is `signal(SIGPIPE, SIG_IGN)` at `library/net_sockets.c:112`, in the socket setup path on non-Windows. It is not threading, but it changes process state.

**Who protects what, when threading is on**

Under the threaded build, each module guards its own shared state with a per-context or file-scope mutex. The mutex is the wrapper from `threading.c`, which defaults to pthreads (`threading.c:103`) and can be replaced with `THREADING_ALT`.

| Mutex | Protects |
|---|---|
| `entropy` `ctx->mutex` | Entropy source list and accumulator (`entropy.c` lock/unlock around lines 93–374) |
| `ctr_drbg` `ctx->mutex` | DRBG state around the random call (`ctr_drbg.c:703–711`) |
| `hmac_drbg` `ctx->mutex` | DRBG state (`hmac_drbg.c:388–396`) |
| `memory_buffer_alloc` `heap.mutex` | Heap allocator bookkeeping (`memory_buffer_alloc.c:540–604`) |
| `mbedtls_threading_gmtime_mutex` | `gmtime` calls, since the fallback is not reentrant (`platform_util.c:189–201`) |
| PSA `rngdata`, `globaldata`, `key_slot` mutexes | PSA RNG state, global PSA data, and key slot table (`psa_crypto.c` at lines 130–165, 2022–2045, 8030+) |

The SSL cache and session ticket headers also gate their thread-safe paths on `MBEDTLS_THREADING_C` (`ssl_cache.h:18`, `ssl_ticket.h:33`). I did not read those bodies.

**What is not protected**

- An SSL, X.509, or cipher context is not locked as a whole. Sharing one across threads needs the caller's own synchronization. The mutexes only cover the shared state inside the modules listed above.
- Under the default build, none of this exists. If several threads use one context, that is the application's problem.

**Caveats on the index**

- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` passed as flags. The `config` search says these are operator-stated and not the repository's default, and no config header is recorded. So the index's 4 thread rows and 1 lock identity describe a threaded build, not the default.
- The lock layer collapsed to a single identity (`mutex->mutex`, low confidence) because the `ctx->mutex` and `heap.mutex` sites are member expressions. I got the per-module list from grep, not from the index.