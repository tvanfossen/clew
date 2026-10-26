Five background threads exist, all spawned from first-party code (`search` threads corpus; the build's spawn patterns, not a full census). Each thread touches shared state through a mutex or an atomic flag.

| Thread | Spawned in | What it does | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` (`src/facade/external_bridge.cpp:796`) | Polls the listen socket, rejects connections from other uids, and starts one serve thread per client | `running_` is atomic and the poll has a 500 ms timeout so shutdown is seen. `client_threads_` is guarded by `client_threads_mutex_`. `SO_PEERCRED` closes cross-uid fds before a thread is spawned. Each client thread closes its own fd. |
| Per-client `serve_client` threads | `accept_loop` (`external_bridge.cpp` ~954) | Serves one JSON-RPC client until disconnect | Each thread owns its fd. `Unsub` guard unsubscribes on exit. `stop()` uses `shutdown(fd)` to wake blocked reads. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` (`src/mcp/health_monitor.cpp:92`) | Every 500 ms, checks watched servers | `watched_mutex_` is held while checking. The wait is on `wake_cv_` with `wake_mutex_`, so stop wakes it immediately. |
| `SSETransport::sse_reader_loop` | `SSETransport::open` (`src/mcp/transport_sse.cpp:107`) | Reads the event stream and feeds `process_sse_line` | `running_` and `connected_` are atomics. `open()` sleeps 500 ms, then checks `connected_`. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` (`src/mcp/transport_stdio.cpp:164`) | Forwards child stderr to a WARNING log | Loops on `connected_`, polls with a 500 ms timeout, and only reads its own `stderr_fd_`. |

A test-only thread (`listen_after_bind` in `transport_sse_test.cpp`) is also indexed. It does not run in production.

**Callbacks don't run on the monitor thread.** `HealthMonitor::process_events` (`health_monitor.cpp:118`) says it runs on the engine thread. The monitor thread queues events, and `process_events` swaps the queue out under `event_mutex_`, then invokes `status_callback_` after releasing the lock. The lock is held only for the swap, so the callback runs without it.

**Cross-thread state.** `ExternalBridge::start` refuses a socket path already bound in this process. It checks and inserts into a process-wide set under `s_bound_sockets_mu` before creating the socket, so two handles can't race onto the same path. Each spawned thread also installs the owning handle's log scope so its log lines reach the right session.

**Lock ordering.** The index reports three two-lock nestings, and no pair is taken in opposite orders, so it shows no deadlock risk. Two of the three are weak:
- `event_mutex_` → `adapter_mutex_` in `process_events` is almost certainly a false edge. The body only swaps `event_queue_` (a `std::vector` swap) under `event_mutex_`, and never touches `AdapterManager`. The index marks it unverified (`resolved_sites=0`).
- `auth_mutex_` → `key_mutex_` in `check_access` goes through `has_access`, which is an unverified receiver. The body shows no direct nesting.
- The third nesting is from a test mock.

**Gaps.** I did not read the bodies of `StdioTransport::open`, `SSETransport::pending_mutex_` usage, or `check_server`, so I can't say how stdio request/response I/O is locked beyond `io_mutex_` existing. The index's spawn-site confidence is `medium` for all five threads.