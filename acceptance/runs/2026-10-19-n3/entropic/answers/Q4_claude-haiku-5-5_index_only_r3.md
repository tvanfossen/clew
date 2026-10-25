The index shows five thread spawn sites, all `pthread`-kind, and all in this repository. Four are production threads and one is a test helper. The index only sees the primitives its patterns match, so these are the sites it found, not a guaranteed census.

| Thread | Spawned in | What it does | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start`, `src/facade/external_bridge.cpp:796` | Polls the listen socket with a 500 ms timeout, checks `SO_PEERCRED` uid, then spawns one `std::thread` per client running `serve_client`. | Each client gets its own thread and fd, so one stuck client doesn't block accept. The client thread list is guarded by `client_threads_mutex_` (RAII, exclusive) while it pushes and reaps finished entries. Each client thread closes its fd and sets `finished`. `stop()` calls `shutdown(fd)` to unblock reads. Each client thread also copies the handle's log scope. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start`, `src/mcp/health_monitor.cpp:92` | Every 500 ms, walks `watched_` and calls `check_server` on due entries. | Iteration over `watched_` is under `watched_mutex_`. The sleep uses `wake_cv_` with `wake_mutex_`, and the predicate is `!running_`, so shutdown wakes it promptly. Results go out through an event queue. `process_events` swaps `event_queue_` out under `event_mutex_`, then invokes the status callback on the engine thread, outside the lock. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open`, `src/mcp/transport_stdio.cpp:164` | Polls child stderr and logs each chunk as a warning. | Only reads its own fd. The loop exits when `connected_` clears or the read returns ≤0. It takes no locks, and the index shows no shared state it touches. |
| `SSETransport::sse_reader_loop` | `SSETransport::open`, `src/mcp/transport_sse.cpp:107` | Runs a blocking HTTP GET for the event stream and feeds each line to `process_sse_line`. | The callback returns `running_.load()` to stop the stream. Shared state goes through `process_sse_line`, which the index does not expand. `SSETransport` has a `pending_mutex_` with 2 acquisitions, but I could not confirm what it guards. |

The fifth row is `listen_after_bind` in `tests/unit/mcp/transport_sse_test.cpp`, which is a test server thread.

**Lock ordering.** The index found 45 distinct lock identities and 3 nested pairs. It reports no opposite-order pair, so it flags no deadlock. That is weak evidence, though, because every pair rests on unverified receivers:

- `event_mutex_` → `adapter_mutex_` (`HealthMonitor::process_events`, 1 site, 0 resolved). This looks like a name collision. Inside the lock, `process_events` only calls `events.swap(event_queue_)` on a vector. The index likely matched that `swap` to `AdapterManager`'s, so this nesting is probably spurious.
- `auth_mutex_` → `key_mutex_` (`MCPAuthorizationManager::check_access`, 4 sites, 0 resolved).
- `mu_` → `adapter_mutex_` (test-only `MockSSEServer`).

**Caveats.** I could not confirm whether `running_` and `connected_` are atomic, and the index doesn't say. The per-client `std::thread` spawned inside `accept_loop` is not listed as its own thread row; it is visible only in the source of `accept_loop`. The index also doesn't show what `SSETransport::pending_mutex_` guards.