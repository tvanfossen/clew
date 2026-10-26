Five spawn sites in this repository start background threads. The index's own count is 5 first-party, 0 vendored. Four are in production code and one is in test code.

**Threads outside the caller's**

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `src/facade/external_bridge.cpp:796` (`ExternalBridge::start`) | Polls the listen socket every 500 ms, rejects peers whose uid doesn't match (`SO_PEERCRED`, gh#34), and hands each accepted fd to its own per-client thread. |
| per-client `serve_client` thread | `accept_loop`, `external_bridge.cpp` ~line 950 (`std::thread` lambda) | Runs `serve_client`: subscribes the fd, reads JSON-RPC lines, dispatches them, and unsubscribes on exit. The index does not list this as a separate thread row. |
| `HealthMonitor::monitor_loop` | `src/mcp/health_monitor.cpp:92` (`HealthMonitor::start`) | Every 500 ms, under `watched_mutex_`, checks each watched MCP server that is due and calls `check_server`. |
| `StdioTransport::stderr_reader_loop` | `src/mcp/transport_stdio.cpp:164` (`StdioTransport::open`) | Reads the child process's stderr and forwards it to the logger as warnings. |
| `SSETransport::sse_reader_loop` | `src/mcp/transport_sse.cpp:107` (`SSETransport::open`) | Holds the SSE GET open and feeds each chunk to `process_sse_line`. |
| `listen_after_bind` | `tests/unit/mcp/transport_sse_test.cpp:98` | Test-only mock server; not production code. |

**What keeps it safe**

- **Shared state is behind named mutexes.** The index lists 45 distinct lock identities in this repository. The ones on these paths are:
  - `ExternalBridge`: `client_threads_mutex_`, `tasks_mutex_`, `subscribers_mutex_`, `s_bound_sockets_mu`.
  - `HealthMonitor`: `watched_mutex_`, `wake_mutex_` (with a condition variable), `event_mutex_`.
  - `StdioTransport`: `io_mutex_`.
  - `SSETransport`: `pending_mutex_`.
  - Each is taken with RAII `lock_guard`/`unique_lock`. For example, `accept_loop` takes `client_threads_mutex_` only around the push and the reap.
- **Shutdown uses atomics and timeouts, not forced kills.** `accept_loop` checks `running_.load()` and polls with a 500 ms timeout. The per-client thread is woken on `stop()` by `shutdown(fd, SHUT_RDWR)`. `monitor_loop` sleeps on `wake_cv_` with a predicate on `running_`. `stderr_reader_loop` polls on a 500 ms timeout while `connected_` is set.
- **Per-client lifetime is tracked.** Each `ClientThread` holds its fd and a `finished` flag. `reap_finished_clients_locked()` joins and erases finished entries. The `Unsub` guard unsubscribes the fd even if `serve_client` exits early.
- **Log context follows the thread.** The per-client thread opens a `HandleLogScope` with the owning handle's `log_id`, so its logs go to that handle's session log.
- **Ordering.** The index records two nested-lock pairs in the health and auth paths: `event_mutex_` → `adapter_mutex_` in `HealthMonitor::process_events`, and `auth_mutex_` → `key_mutex_` in `MCPAuthorizationManager::check_access`. Neither pair is taken in the opposite order anywhere, so no inversion appears in the index. However, every site behind those pairs has an unverified receiver, so I would not call the ordering confirmed.

**Gaps in what I could verify**

- The index does not show whether `running_` in `monitor_loop` and `connected_` in the stderr and SSE readers are `std::atomic`. `accept_loop` uses `.load()`, but I could not confirm the declared types of the others. The stop path depends on them being safe to read across threads, so check their declarations.
- The per-client thread was not detected as a spawn site, so the index's thread count of 5 is an undercount of what actually runs.