# Q3 — src — sonnet — run 1

## Answer

Yes — but only in **example/demo programs and test code**, not in the core `library/` (the TLS/crypto engine itself never spawns a thread; it only exposes a mutex abstraction for callers who are already multithreaded).

**1. `programs/ssl/ssl_pthread_server.c` — POSIX threads per SSL connection (the main case)**
- A per-connection worker thread is spawned with `pthread_create(&threads[i].thread, NULL, handle_ssl_connection, &threads[i].data)` in `thread_create()` at `programs/ssl/ssl_pthread_server.c:277`.
- The thread entry point is `handle_ssl_connection` (`programs/ssl/ssl_pthread_server.c:98`), which: initializes an `mbedtls_ssl_context` (`:108`), runs `mbedtls_ssl_setup`/`mbedtls_ssl_handshake` (`:115`, `:129`), reads the client's HTTP request via `mbedtls_ssl_read` (`:148`), writes a canned HTTP response via `mbedtls_ssl_write` (`:192`), then frees the connection and marks itself done (`:238-241`) before returning `NULL`.
- `main()` accepts connections in a loop and calls `thread_create()` for each one, reaping finished slots with `pthread_join` (`programs/ssl/ssl_pthread_server.c:260`). This whole file is gated behind `MBEDTLS_THREADING_C`/`MBEDTLS_THREADING_PTHREAD` — if pthread threading support isn't configured in, `main()` just prints a message and exits (`programs/ssl/ssl_pthread_server.c:24-29`), so no thread is created in that build configuration.

**2. `programs/test/benchmark.c` — a Windows timer thread**
- On `_WIN32` builds, `mbedtls_set_alarm(int seconds)` spawns a thread via `_beginthread(TimerProc, 0, NULL)` at `programs/test/benchmark.c:430`, but only when `seconds != 0` (`:421-426`).
- The thread body `TimerProc` (`programs/test/benchmark.c:410`) just sleeps for `alarmMs` milliseconds then sets the global flag `mbedtls_timing_alarmed = 1` (`:413-414`) — it's a one-shot alarm/watchdog timer for the benchmark harness, not connection handling. On non-Windows, the same alarm is implemented with `signal()`/`alarm()` instead (`programs/test/benchmark.c:435` onward), no thread involved.

**What core `library/` does instead:** `library/threading.c` (matched in the broader grep) only wraps `pthread_mutex_*` calls behind `mbedtls_threading_mutex_init/free/lock/unlock` — it never calls `pthread_create`. This confirms the library is designed to be thread-*safe* (with mutexes) but not thread-*creating*; threading is left entirely to the application, as demonstrated by the two programs above.

## Confidence

High for both findings — both are direct, unambiguous calls to platform thread-creation APIs (`pthread_create`, `_beginthread`), found via a repo-wide grep for `pthread_create|CreateThread|_beginthread|thrd_create|std::thread` with no other hits in `.c`/`.h`/`.cpp` files. Confirmed by reading the surrounding code and the thread entry-point bodies directly.

## Gaps

- I did not exhaustively read every file under `tests/suites/` beyond the pattern grep (e.g. `test_suite_platform_threading.function` matched `mbedtls_threading` references but no `pthread_create` calls) — it's plausible some test-only thread usage exists behind a helper wrapper with a name my grep didn't catch, but a targeted grep for `thread_create`/`thread_func`/`thread_start_routine` in that file found nothing.
- I did not check `tests/include/alt-dummy/threading_alt.h` in depth — it appeared in the broader grep but by name looks like an alternate mutex-only threading implementation stub, consistent with the "library never creates threads" conclusion; I did not open it to confirm.
