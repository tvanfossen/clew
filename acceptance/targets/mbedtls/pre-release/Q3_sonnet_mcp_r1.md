# Q3 — mcp — sonnet — run 1

This confirms only the two thread-related sites already found (48 matches for "thread" generally, consistent with mutex/threading.c infrastructure but not new spawn sites). I have enough to answer.

## Answer

Yes — mbedtls creates threads in two places, both in example/test programs, not in the core cryptography library:

**1. POSIX pthread — `programs/ssl/ssl_pthread_server.c`**
- `thread_create()` (`programs/ssl/ssl_pthread_server.c:246-283`) calls `pthread_create(&threads[i].thread, NULL, handle_ssl_connection, &threads[i].data)` at `programs/ssl/ssl_pthread_server.c:277`.
- The spawned thread runs `handle_ssl_connection()` (`programs/ssl/ssl_pthread_server.c:98-244`), which does the actual per-connection work: `mbedtls_ssl_init`/`mbedtls_ssl_setup`/`mbedtls_ssl_set_bio`, a handshake loop calling `mbedtls_ssl_handshake` (`ssl_pthread_server.c:127`), a read loop calling `mbedtls_ssl_read` (`ssl_pthread_server.c:158`), a write of a canned HTTP response via `mbedtls_ssl_write` (`ssl_pthread_server.c:189-194`), then `mbedtls_ssl_close_notify`/`mbedtls_ssl_free`.
- `thread_create()` is itself called from `main()` (`programs/ssl/ssl_pthread_server.c:2244` per index rowid — i.e. in `main`, same file) once per accepted client connection, so this is a one-thread-per-connection SSL demo server.
- Gated by `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` (`programs/ssl/ssl_pthread_server.c:30`), so this code path only compiles/runs when those config options are enabled.

**2. Win32 `_beginthread` — `programs/test/benchmark.c`**
- `mbedtls_set_alarm()` (the `_WIN32`/non-EFI variant, `programs/test/benchmark.c:419-431`) calls `_beginthread(TimerProc, 0, NULL)` at `programs/test/benchmark.c:430`.
- The spawned thread runs `TimerProc()` (`programs/test/benchmark.c:410-417`), which just does `Sleep(alarmMs)` then sets `mbedtls_timing_alarmed = 1` — implementing a software alarm/timeout for the benchmark tool on Windows (where `alarm()`/`SIGALRM` aren't available; the POSIX fallback at `programs/test/benchmark.c:441-451` uses `signal`+`alarm` instead, no thread).
- Gated by `_WIN32 && !EFIX64 && !EFI32` (`programs/test/benchmark.c:405`) and `MBEDTLS_HAVE_TIME`/`!MBEDTLS_TIMING_ALT` (`programs/test/benchmark.c:18,239`).

**Confidence:** High that these are the two thread-spawn sites in the tree, medium on the index's own tagging (`confidence: medium` on both thread rows from the AST-spawn detector). I corroborated both hits by reading the actual source (`ssl_pthread_server.c:246-283`, `benchmark.c:400-454`), so the call sites and functions-run are directly verified, not just inferred from the index. I also re-searched for `pthread_create`/`thread` symbol names and found no additional first-party spawn sites beyond these two and the `threading.c` mutex-abstraction machinery (48 "thread"-token hits, all consistent with these two spawns plus threading primitives, not new thread-creation calls).

No core library code (`library/`) spawns threads — thread creation is confined to `programs/` (a demo SSL server and a benchmarking tool). `library/threading.c` provides mutex abstractions used *by* threaded callers but does not itself create threads.

## Gaps
- The index's thread-spawn detector is a fixed pattern set (pthread, std::thread/jthread, Win32 primitives, RTOS primitives like `xTaskCreate`); a thread creation mechanism outside that set (e.g. a custom wrapper, or a spawn hidden behind a function pointer / macro not covered by the AST-spawn heuristic) would not surface here. I did not do an exhaustive manual grep of all 527 indexed files for alternate spawn APis (e.g. `CreateThread`, `_beginthreadex`, RTOS calls) — the `thread`-token search (48 hits) is corroborating evidence, not a proof of completeness.
- Did not verify whether these threading example programs are built by default (CMake/Makefile conditionals) — only confirmed the compile-time macro gates in source.
