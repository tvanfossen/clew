Five spawn sites in this repo are indexed as background threads, and the safety comes from per-state mutexes, a stop sequence that joins everything, and a few lock-order checks. The index is incomplete for `std::thread`, so the list below is a floor, not a full inventory.

**Background threads (indexed)**

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start`, `src/facade/external_bridge.cpp:796` | Polls the listen socket, rejects peers whose uid doesn't match (`SO_PEERCRED`), and gives each client its own thread. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start`, `src/mcp/health_monitor.cpp:92` | Checks watched MCP servers every 500 ms. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open`, `src/mcp/transport_stdio.cpp:164` | Reads the child process's stderr. |
| `SSETransport::sse_reader_loop` | `SSETransport::open`, `src/mcp/transport_sse.cpp:107` | Reads the SSE stream. |

Per-client serve threads and the detached `ExternalBridge::run_async_ask` worker (which runs `entropic_run` for an async ask) are documented as threads, but the index does not list them. `run_async_ask` shows no thread entry at all, so the index can't confirm its threading. The per-client threads appear only as an inline `std::thread` inside `accept_loop`. Treat the five above as the indexed set, not the whole set.

**What keeps it safe**

- **Each shared structure has its own mutex.** Examples: `tasks_mutex_` guards the async task map, which `run_async_ask`, `update_task_phase`, `handle_ask_status`, and `cleanup_expired_tasks` all touch. `subscribers_mutex_` guards subscriber notifications. `client_threads_mutex_` guards the client-thread vector. `watched_mutex_` guards the watch list that `monitor_loop` iterates while `watch` and `unwatch` modify it.
- **Work is handed off through swaps, not held locks.** `HealthMonitor::process_events` swaps the event queue out under `event_mutex_`, then runs the callbacks after releasing it. Callbacks never run under the lock.
- **Shutdown is ordered.** `ExternalBridge::stop` sets `running_` to false, closes the listen fd, and joins the accept thread, so no new client threads can appear. It then `shutdown(SHUT_RDWR)`s each client fd so blocking reads return, and joins each client thread. `HealthMonitor` uses a condition variable on `wake_mutex_` with a `running_` predicate, so it wakes at once on stop.
- **Ownership is explicit.** Client threads hold a raw pointer into a `unique_ptr` stored in `client_threads_`. That is safe only because the pointer is removed after the thread is joined, which `reap_finished_clients_locked` and `stop` do. The `finished` atomic is the handshake.
- **Ordering for observers.** `run_async_ask` writes the completion sentinel file while holding `tasks_mutex_`, before the progress notification goes out, so a watcher reacting to the sentinel sees the final task state.
- **Logs stay with their handle.** Each spawned thread captures `log_id` and opens a `HandleLogScope`, so its logs route to the owning session.
- **Port claims are global.** `s_bound_sockets_mu` guards the set of bound socket paths, so two handles in one process can't bind the same path.

**Lock-order check**

The index shows three two-lock nestings, and none is taken in opposite orders, so it finds no deadlock pair:
- `auth_mutex_` → `key_mutex_` in `check_access` (4 sites).
- `event_mutex_` → `adapter_mutex_` in `process_events`, and `mu_` → `adapter_mutex_` in a test helper. These two are unverified: the receiver wasn't resolved (`resolved_sites=0`).

The index only records observed nestings, so this is evidence, not a proof that no deadlock exists.