Five spawn sites in this repo start threads that run concurrently with their caller. Four are production code and one is test code. The safety rests on atomic run flags, a few mutexes that each guard one structure, and one drain-then-dispatch handoff back to the engine thread. I found no reversed lock orders, but the lock-order evidence is thin (details below).

**Threads that run off the caller's thread**

| Thread | Spawned in | What it does | Stop/sync mechanism |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start`, `src/facade/external_bridge.cpp:796` | Polls the listen socket, checks peer uid, spawns one serve thread per client | `running_` (atomic), 500 ms `poll` timeout |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start`, `src/mcp/health_monitor.cpp:92` | Periodically runs `check_server` on each watched server | `running_` (atomic), `wake_cv_` wait on `wake_mutex_` |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open`, `src/mcp/transport_stdio.cpp:164` | Forwards child stderr to the log | `connected_` (atomic), 500 ms `poll` |
| `SSETransport::sse_reader_loop` | `SSETransport::open`, `src/mcp/transport_sse.cpp:107` | Blocking HTTP GET on the SSE stream, parses lines | `running_` and `connected_` (atomic) |
| `listen_after_bind` | `MockSSEServer`, `tests/unit/mcp/transport_sse_test.cpp:98` | Test fixture only | — |

The index reports these five as pthread spawn sites. It also shows a sixth thread the index does not list: `accept_loop` creates a per-client `std::thread` (around `external_bridge.cpp:947`) that runs `serve_client`. The index's spawn patterns did not match it, so the five-site count is not a complete census.

**What keeps them safe**

1. **Stop flags are atomic.** `running_` and `connected_` are `std::atomic<bool>` in the headers. The per-client `finished` flag is also atomic and is set by the thread itself before it exits.

2. **Each shared structure has its own mutex, held briefly.**
   - `HealthMonitor::monitor_loop` holds `watched_mutex_` while it walks `watched_` and calls `check_server`.
   - `ExternalBridge::accept_loop` holds `client_threads_mutex_` only while it pushes the new client and calls `reap_finished_clients_locked()`, which joins and erases finished clients.

3. **Drain then dispatch.** `HealthMonitor::process_events` swaps `event_queue_` out under `event_mutex_` and then invokes `status_callback_` outside the lock. Its header says the callbacks run on the engine thread. The background thread only enqueues, so user callbacks never run on the monitor thread.

4. **Clean shutdown wakes blocked threads.** The monitor uses a condition variable so `stop` can wake it immediately. The socket readers use 500 ms `poll` timeouts so they re-check their flags. The bridge's `stop()` calls `shutdown(fd, SHUT_RDWR)` to unblock a `read` in a serve thread.

5. **Security and observability gates.** Each accepted fd passes `SO_PEERCRED` (`peer_uid_matches`) before a serve thread is created. The handle's log scope is copied into each client thread so its logs stay attached to the right session.

**Gaps**

- **Lock ordering is unverified.** The index found three two-lock nestings (`event_mutex_` → `AdapterManager::adapter_mutex_`, `auth_mutex_` → `MCPKeySet::key_mutex_`, and the test's `MockSSEServer::mu_` → `adapter_mutex_`). None appear in reverse order. However, all three have zero resolved call sites, so the nesting claims rest on unverified receivers. Treat "no deadlock risk" as unconfirmed.
- **`status_callback_` is not shown to be synchronized.** The dispatch reads it on the engine thread, and I did not check whether it is written elsewhere.
- **`ExternalBridge::start` is not indexed under that qualified name.** I read `accept_loop` and its spawn site through the thread record instead.