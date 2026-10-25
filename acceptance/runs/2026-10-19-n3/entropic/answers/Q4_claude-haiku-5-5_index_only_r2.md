The index shows five background-thread spawn sites in entropic's own code. Each one is guarded by a single mutex or atomic flag, and the index shows no deadlock. It is not a full audit, though: some lock-ordering evidence is unverified, and the spawn scan only covers primitives its patterns match.

**Background threads**

| Thread | Spawned in | What it does | What makes it safe |
|---|---|---|---|
| `ExternalBridge` accept loop (`accept_loop`) | `ExternalBridge::start`, `src/facade/external_bridge.cpp:796` | Polls the listen socket every 500 ms, checks peer uid via `SO_PEERCRED`, and spawns one serve thread per client. | `running_` atomic is the shutdown flag. New client threads go into `client_threads_` under `client_threads_mutex_`. `start()` claims the socket path under `s_bound_sockets_mu` before binding, so two handles in one process can't share a path. Each thread installs a `HandleLogScope` so its logs go to the right session. |
| Per-client serve threads | Spawned inside `accept_loop`'s lambda (not a separate row in the index) | Serve one MCP client, then close their fd and set `finished`. | Shutdown uses `shutdown(fd, SHUT_RDWR)` to wake blocked reads. Finished threads are joined and removed by `reap_finished_clients_locked()` under `client_threads_mutex_`. Async task state is guarded by `tasks_mutex_`. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start`, `src/mcp/health_monitor.cpp:92` | Every 500 ms, runs `check_server` on servers whose next action is due. | Watched-server map is guarded by `watched_mutex_`. The wait uses `wake_cv_` with `wake_mutex_`, and exits when `running_` goes false. Event queue is guarded by `event_mutex_`. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open`, `src/mcp/transport_stdio.cpp:164` | Reads the child process's stderr and forwards it to the logger at WARN. | Loops on `connected_`, polls with a 500 ms timeout so it can exit. Pipe writes are serialized by `io_mutex_`. |
| `SSETransport::sse_reader_loop` | `SSETransport::open`, `src/mcp/transport_sse.cpp:107` | Runs the blocking HTTP SSE GET and parses events. | Responses are handed off through `pending_responses_`, guarded by `pending_mutex_`. Ends when the receiver returns `running_`, and sets `connected_` false on exit. |

There is also a spawn in `tests/unit/mcp/transport_sse_test.cpp:98` (`MockSSEServer`). It is test-only.

**Lock-ordering evidence**

The index found 45 distinct lock identities, 3 of which are nested. All are in one direction, so none is an observed deadlock:

- `HealthMonitor::event_mutex_` → `AdapterManager::adapter_mutex_` (in `process_events`, `health_monitor.cpp:122`)
- `MCPAuthorizationManager::auth_mutex_` → `MCPKeySet::key_mutex_` (in `check_access`, `mcp_authorization.cpp:105`, 4 sites)
- Test mock `mu_` → `adapter_mutex_`

Two caveats. First, every one of those pairs has `resolved_sites=0`, so the receiver calls were never verified. Second, `process_events` is not in the index, so I could not confirm its body. Treat the ordering as "no reverse pair observed", not as proven.

**Gaps**

- The index only counts spawn calls its patterns match. Other thread-creation primitives would be missed silently.
- Some of the per-client threads are created inside the accept-loop lambda, so they appear only through the `accept_loop` body, not as their own thread row.