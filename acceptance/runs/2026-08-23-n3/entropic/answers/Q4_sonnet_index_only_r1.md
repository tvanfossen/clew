## Threads that run off the caller's thread

The index resolves 5 real spawn sites (a 6th, `listen_after_bind`, is test-harness-only in `transport_sse_test.cpp` and not part of the shipped binary):

**1. `ExternalBridge::accept_loop`** — spawned from `ExternalBridge::start()` (`src/facade/external_bridge.cpp:796`). It polls the listen socket and, per accepted connection, spawns a *second* generation of thread inline via `std::thread([...]{ serve_client(fd); ... })` — so a connecting MCP client gets its own dedicated thread (`ClientThread`), tracked in `client_threads_`. `serve_client` calls `subscribe`/`unsubscribe` and `dispatch`/`write` on that per-client thread.

**2. `HealthMonitor::monitor_loop`** — spawned from `HealthMonitor::start()` (`src/mcp/health_monitor.cpp:92`). Polls watched servers every 500ms, calling `check_server` → `attempt_reconnect` / `post_event`.

**3. `StdioTransport::stderr_reader_loop`** — spawned from `StdioTransport::open()` (`src/mcp/transport_stdio.cpp:164`). Drains a child process's stderr fd and forwards lines to spdlog at WARNING.

**4. `SSETransport::sse_reader_loop`** — spawned from `SSETransport::open()` (`src/mcp/transport_sse.cpp:107`). Runs the blocking `httplib` SSE `Get`, parsing lines out of the streaming callback into `process_sse_line` → `handle_sse_data`.

## What keeps each one safe

The mechanisms differ by thread and the index shows each concretely rather than as a general policy:

- **`accept_loop` / per-client threads:** `client_threads_mutex_` (class `ExternalBridge`) is taken as a RAII `lock_guard` around every mutation of the `client_threads_` vector (push_back + `reap_finished_clients_locked()`), so the accept thread and the reaping path never touch that container unsynchronized. Each per-client thread flips an `finished` flag on exit rather than mutating the vector itself, which the accept thread then reaps under the same lock. Separately, `subscribers_mutex_` and `tasks_mutex_` (both `ExternalBridge`) exist to protect the subscriber/task state that `subscribe`/`dispatch` touch from whichever client thread is running — the index records these as distinct lock identities with real acquisition counts (4 and 7 respectively) but I can't tell you from the graph alone whether every touch of those members is actually gated; that would need reading `subscribe`/`dispatch`/`unsubscribe` directly.
- **`monitor_loop`:** `watched_mutex_` guards the `watched_` map iteration/mutation inside the loop, and a **separate** `wake_mutex_` backs a condition variable (`wake_cv_.wait_for`) used purely for interruptible sleep/shutdown signaling — the loop deliberately doesn't hold `watched_mutex_` while waiting on the CV, avoiding a hold across the sleep. `running_` is checked as the CV predicate, consistent with the project's stated pattern of atomics for state queries.
- **`stderr_reader_loop`:** no lock at all in the loop body — it owns a private fd (`stderr_fd_`) that nothing else reads, and only calls `logger->warn`, so safety here comes from **fd exclusivity plus a thread-safe logging sink** rather than an explicit mutex. (`io_mutex_` exists on `StdioTransport` but the index shows no acquisition inside this specific function — it's presumably scoped to guarding the stdin/stdout path used by the main thread, not stderr.)
- **`sse_reader_loop`:** likewise no lock inside the loop itself; it owns the `httplib` client and streams into `process_sse_line`. `SSETransport` does declare a `pending_mutex_` (2 acquisitions) elsewhere in the class, which by name is guarding whatever cross-thread handoff state (`pending_...`) exists between this reader thread and consumers — the index doesn't show that acquisition occurring inside `sse_reader_loop`'s own body, so the boundary is presumably in `process_sse_line`/`handle_sse_data`, one hop further than I traced.

**Gap I can't close from the index alone:** the graph tells you *which* mutex guards *which* critical section per function, but not whether the full set of shared members each thread touches is consistently covered — that requires reading `subscribe`, `dispatch`, `check_server`, and `process_sse_line` directly rather than trusting lock-identity counts as proof of complete coverage.
