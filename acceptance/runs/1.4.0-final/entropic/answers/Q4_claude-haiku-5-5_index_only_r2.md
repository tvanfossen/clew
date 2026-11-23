The index shows about ten background thread spawn sites in entropic, and most of them are guarded by a small set of per-object mutexes plus a few shutdown and ordering rules. I answered from the index alone, so I could not read the full bodies of every spawn site.

**Which parts run off the caller's thread**

| Thread | Spawned at | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` (from `start`) | Polls the listen fd every 500 ms, checks peer uid, and spawns one serve thread per client. |
| Per-client serve thread (`ct->thread`) | `external_bridge.cpp:945` | Runs `serve_client`, which reads JSON-RPC lines and writes replies. |
| `ExternalBridge::run_async_ask` worker | `external_bridge.cpp:1158` | Runs `entropic_run` for an async `entropic.ask`, then updates the task registry and broadcasts progress. |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` (from `start`) | Background health checks. |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Drains a child process's stderr. |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Reads the SSE stream. |
| Cancel pollers (3 sites) | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` | 10 ms polls that mirror an interrupt flag into the C-ABI `int*` for one call. |

**What keeps it safe**

- **Task registry:** `tasks_mutex_` guards `tasks_`. The worker writes the terminal status and the completion sentinel under that lock, before the progress notification goes out, so `ask_status` can't see a state that disagrees with the notification.
- **Client thread list:** `client_threads_mutex_` guards `client_threads_`. `accept_loop` pushes and reaps under it, and `stop()` moves the list out under it before joining.
- **Subscribers:** `broadcast_notification` copies the subscriber set under `subscribers_mutex_`, releases the lock, then sends with `MSG_DONTWAIT | MSG_NOSIGNAL`. Slow or dead fds are dropped, and dead ones are removed under the lock again. A slow client can't wedge the sender, at the cost of losing that notification.
- **Access control:** `accept_loop` checks `SO_PEERCRED` and closes cross-uid connections before any serve thread exists.
- **Shutdown ordering in `stop()`:** clear `running_`, close the listen fd, join the accept thread, shut down each client fd to unblock its read, join the client threads, then remove the socket file and release the bound-socket claim under `s_bound_sockets_mu`.
- **Cancel pollers:** they use atomics, and the spawner joins each poller before the locals it captured by reference go out of scope.
- **Health events:** `process_events` swaps the queue out under `event_mutex_` and runs the callbacks after releasing it, on the engine thread rather than the monitor thread.
- **Logging:** `HandleLogScope` is carried into the worker and per-client threads (gh#59), so their logs land in the owning handle's session log.

**Caveats**

- `run_async_ask`'s worker is a `std::thread` whose lambda captures `this`. The body I read was truncated before any `join()` or `detach()`, and `stop()` does not wait for async workers. Whether an in-flight ask outlives `ExternalBridge` is unverified; check the end of that lambda.
- The lock-nesting report lists three two-lock orderings, and all three have `resolved_sites=0`, so none is confirmed. The one it attributes to `HealthMonitor::process_events` doesn't match the body: `process_events` takes only `event_mutex_`. I would not cite that pair.
- The thread count is the set of spawn sites matched by this build's patterns, not a guarantee that no other spawn primitive exists.