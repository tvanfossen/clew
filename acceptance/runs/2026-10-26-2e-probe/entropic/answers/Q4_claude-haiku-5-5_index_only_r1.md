The index shows five thread spawn sites in entropic's own code. Four are real background loops, and one is a test helper. What keeps them safe is mostly ownership and locking discipline inside each component. I could not confirm lock ordering: the index's nested-lock pairs are unverified.

**Background threads**

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start`, `src/facade/external_bridge.cpp:796` | Polls the listen socket every 500 ms and accepts MCP clients. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start`, `src/mcp/health_monitor.cpp:92` | Checks watched MCP servers every 500 ms or on wake. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open`, `src/mcp/transport_stdio.cpp:164` | Drains the child process's stderr. |
| `SSETransport::sse_reader_loop` | `SSETransport::open`, `src/mcp/transport_sse.cpp:107` | Blocks on the SSE stream and parses events. |
| `listen_after_bind` | `MockSSEServer`, test code only | Test fixture. |

Each row is detected by spawn pattern and rated "medium" confidence. The count is exact only for the primitives the index matches. The index also misses the per-client serve threads: `accept_loop` creates them with `ct->thread = std::thread(...)`, but they do not appear as rows.

**What keeps them safe**

- **Bridge socket ownership.** `ExternalBridge::start` claims the canonical socket path in a process-wide set (`s_bound_sockets`) under `s_bound_sockets_mu` before it unlinks or binds. Two handles in one process cannot steal each other's socket.
- **Client-thread bookkeeping.** `accept_loop` pushes and reaps `client_threads_` only under `client_threads_mutex_`. Each client thread closes its own fd, then sets an atomic `finished` flag for the reaper to join.
- **Access control before spawn.** Each accepted fd is checked with `peer_uid_matches` (SO_PEERCRED) and closed before a serve thread is created.
- **Shutdown.** `running_` is atomic. `HealthMonitor` waits on `wake_cv_` under `wake_mutex_`, so `stop()` wakes it instead of waiting out the poll. The bridge's `stop()` calls `shutdown(fd)` to unblock reads.
- **Health checks.** `monitor_loop` runs `check_server` for each watched entry while holding `watched_mutex_`.
- **Health events.** `process_events` swaps the queue out under `event_mutex_`, then invokes callbacks with no lock held. The header says callbacks run on the engine thread, so the monitor thread never runs engine callbacks.
- **Log routing.** The bridge captures `handle_->log_id` and installs a `HandleLogScope` in each thread body, so its logs reach the owning handle's session log.

**Caveats**

- **Lock nesting is unconfirmed.** The index reports three nested lock pairs, and all three have `resolved_sites=0`. Two look like misresolved `swap` calls: `process_events` only swaps `event_queue_` under `event_mutex_`, and the body shows no nested acquisition. I cannot claim a lock order, and I cannot rule out a deadlock from this index.
- **Not traced.** The index lists `pending_mutex_` in `SSETransport` (2 acquisitions) and `io_mutex_` in `StdioTransport` (1 acquisition). I did not read the code that uses them, so I cannot say what they protect.