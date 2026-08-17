# Q3 — mcp — haiku — run 1

## ANSWER

**Yes, mbedtls creates threads. There are exactly 2 thread spawn sites detected in the repository.**

### Thread 1: SSL Connection Handler (Unix/Linux)

- **Spawned at:** `programs/ssl/ssl_pthread_server.c:277`
- **Entry function:** `handle_ssl_connection` 
- **Mechanism:** `pthread_create()` via a wrapper function `thread_create()`
- **What it runs:** An SSL/TLS connection handler. The thread:
  - Initializes an SSL context (`mbedtls_ssl_init`, `programs/ssl/ssl_pthread_server.c:107`)
  - Sets up the SSL connection (`mbedtls_ssl_setup`, `programs/ssl/ssl_pthread_server.c:112`)
  - Performs the SSL/TLS handshake (`mbedtls_ssl_handshake`, `programs/ssl/ssl_pthread_server.c:123`)
  - Reads HTTP requests from the client (`mbedtls_ssl_read`, `programs/ssl/ssl_pthread_server.c:135-168`)
  - Writes HTTP responses (`mbedtls_ssl_write`, `programs/ssl/ssl_pthread_server.c:185-203`)
  - Closes the connection cleanly (`mbedtls_ssl_close_notify`, `programs/ssl/ssl_pthread_server.c:206`)

### Thread 2: Windows Timer/Alarm (Windows only)

- **Spawned at:** `programs/test/benchmark.c:430`
- **Entry function:** `TimerProc`
- **Mechanism:** `_beginthread()` called from `mbedtls_set_alarm()`
- **What it runs:** A timer thread that:
  - Sleeps for the specified alarm duration (`Sleep(alarmMs)`, `programs/test/benchmark.c:413`)
  - Sets a global flag to signal alarm expiration (`mbedtls_timing_alarmed = 1`, `programs/test/benchmark.c:414`)
  - This is used for timing measurements in the benchmark utility

### Important Context

Both threads are in **example/test programs** (`programs/` directory), not in the core mbedtls library itself. The core library does not create threads directly — these are demonstration/benchmarking programs that use threading for their own purposes.

### Confidence

**HIGH (95%)** — The index detected these via abstract syntax tree analysis of thread spawn primitives (`pthread_create` and `_beginthread`), with "medium" confidence per spawn site. The index found 2 spawn sites with 2 first-party origins and 0 unresolved. This is an exact count for the patterns the build searches. The source code verification confirms both spawn sites exist and function as described.

## Gaps

None. The question is fully answered by the index. Both thread spawn sites have been located with their entry functions, purposes, and mechanisms verified against source.
