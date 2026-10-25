The index shows five thread spawn sites in entropic's own code. Four are production background threads, and one is a test helper.

**Threads other than the caller's**

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` (`src/facade/external_bridge.cpp:796`) | Accepts MCP client connections. Each accepted client gets its own `std::thread` running `serve_client`. |
| `ExternalBridge::serve_client` (one per client) | spawned from `accept_loop` | Reads JSON-RPC lines from one client and dispatches them. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` (`src/mcp/health_monitor.cpp:92`) | Periodically checks watched MCP servers and runs `check_server`. |
| `SSETransport::sse_reader_loop` | `SSETransport::open` (`src/mcp/transport_sse.cpp:107`) | Reads the SSE stream from an MCP server and feeds each line to `process_sse_line`. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` (`src/mcp/transport_stdio.cpp:164`) | Forwards a child MCP process's stderr to the warning log. |
| `listen_after_bind` | `MockSSEServer` (`tests/unit/mcp/transport_sse_test.cpp:98`) | Test-only server thread. |

The index does not show threads for the inference engine, the agent engine's queue, or the adapter manager. That may be a real absence or a gap in the spawn patterns it matches. The index reports that spawns are matched only for the primitives its patterns cover, so I would not claim the engine is single-threaded without checking.

**What keeps it safe**

- **Shutdown flags are atomics.** `running_` is a `std::atomic<bool>` in `ExternalBridge`, `HealthMonitor`, and `SSETransport`. Every loop reads it without taking a lock.
- **Loops wake on a timeout.** `accept_loop` polls its listen fd with a 500 ms timeout. `monitor_loop` waits on a condition variable with a 500 ms `wait_for`, woken early by `wake_mutex_` when `running_` clears. `stderr_reader_loop` polls with a 500 ms timeout.
- **Shared state sits behind mutexes.**
  - `HealthMonitor::watched_mutex_` guards the watch table during `monitor_loop`.
  - `ExternalBridge::client_threads_mutex_` guards the client-thread list. The accept loop holds it only to push and reap.
  - `ExternalBridge::tasks_mutex_` guards the task map, and the index shows it taken in about seven places.
  - `StdioTransport::io_mutex_` and `SSETransport::pending_mutex_` guard their I/O and pending-request state.
- **Each client thread owns its fd.** The per-client thread closes its own fd, sets `finished`, and the accept loop later joins and erases it through `reap_finished_clients_locked()`. `serve_client` uses an RAII guard to unsubscribe on exit.
- **Access control happens before the thread exists.** `accept_loop` checks the peer uid (`SO_PEERCRED`) and closes any connection from another uid before spawning a serve thread.
- **Logging context carries over.** The accept loop captures the handle's log id and reinstalls it in the client thread with `HandleLogScope`.

**Gaps to check**

- The index reports two nested lock pairs as unverified (`resolved_sites=0`). One is `HealthMonitor::event_mutex_` taken before `AdapterManager::adapter_mutex_` in `process_events`. The other is `MCPAuthorizationManager::auth_mutex_` taken before `MCPKeySet::key_mutex_` in `check_access`. The index found no reverse ordering, so it shows no deadlock risk, but it did not confirm the receivers either.
- Several `tasks_mutex_` acquisitions have receivers the index could not verify, so those sections are less certain.
- The `stop()` path, per the `accept_loop` doc, wakes blocked reads with `shutdown(fd, SHUT_RDWR)`. I did not confirm that from the index.