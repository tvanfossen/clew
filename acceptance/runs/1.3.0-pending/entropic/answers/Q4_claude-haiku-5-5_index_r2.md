## Threads that run off the caller's thread

The index finds 10 spawn sites in first-party code. Grouped by lifetime:

| Thread | Spawned in | Lifetime | Shared state it touches |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` (`external_bridge.cpp:796`) | Long-lived, joined in `stop()` | `running_` (atomic), `listen_fd_` |
| Per-client `serve_client` threads | `accept_loop` (`external_bridge.cpp:945`) | One per MCP client, joined in `stop()` | `client_threads_` under `client_threads_mutex_` |
| `run_async_ask` worker | `ExternalBridge::run_async_ask` (`external_bridge.cpp:1158`) | Per `entropic.ask`, **detached** | `tasks_`, under `tasks_mutex_`; runs `entropic_run` on the handle |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` (`health_monitor.cpp:92`) | Long-lived, joined in `stop()` | `event_queue_` under `event_mutex_` |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` | Joined on close (`transport_stdio.cpp:219`) | `io_mutex_` |
| `SSETransport::sse_reader_loop` | `SSETransport::open` | Joined on close (`transport_sse.cpp:139`) | `pending_mutex_` |
| Cancel poller threads | `CancelFlagBridge`, `iface_generate_with_cancel`, `ResponseGenerator::dispatch_batch_generate` | Short-lived, joined before the call returns | Atomic cancel flags only |

The cancel pollers are the simplest case. Each one spins at 10 ms, reads an int or atomic, and sets an atomic `cancel_` flag. The caller sets `done` and joins before returning.

## What keeps it safe

- **Mutex-guarded shared state.** Each shared structure has one lock: `tasks_mutex_`, `client_threads_mutex_`, `event_mutex_`, `adapter_mutex_`, `auth_mutex_`.
- **Swap-then-run.** `HealthMonitor::process_events` swaps the queue out under `event_mutex_`, then runs callbacks outside the lock, on the engine thread.
- **Sentinel ordering.** `run_async_ask` writes the sentinel file under `tasks_mutex_`, before the progress notification fires, so an external monitor that reacts to the sentinel sees the same terminal state the registry holds.
- **Atomics across the ABI.** Cancel and running flags are `std::atomic`. The C ABI passes only `int*`, so no `std::atomic` crosses the `.so` boundary.
- **Ordered shutdown.** `ExternalBridge::stop()` sets `running_=false`, closes the listen fd, joins the accept thread, then `shutdown(SHUT_RDWR)`s each client fd so blocked reads return, and joins each client thread. `entropic_destroy` calls `stop()` before tearing down the rest of the handle.
- **Log routing.** Worker threads take a `HandleLogScope` so their logs land in the owning handle's session log.
- **Lock nesting.** The index reports 45 lock identities and no pair taken in opposite orders, so it shows no deadlock risk.

## The gap

`run_async_ask` ends with `}).detach();` (`external_bridge.cpp:1222`). The detached lambda captures `this` and reads `handle_`, and calls `entropic_run`, `broadcast_notification`, and `cleanup_expired_tasks`. Nothing tracks it. `stop()` does not wait for in-flight async workers, and `entropic_destroy` calls `stop()` and then tears down the handle. A `ask` still running at destroy time can therefore touch a destroyed bridge and handle. I found no in-flight counter or join. This is a likely use-after-free, but I have not confirmed it at runtime, and a test that destroys the handle mid-ask would settle it.

## Two index results to discount

- **`HealthMonitor::event_mutex_ → AdapterManager::adapter_mutex_`** is reported as a nesting, but it is a false match. `process_events` calls `events.swap(event_queue_)` on a `std::vector`, and the index attributed that call to `AdapterManager::swap`. The site has `resolved_sites=0`.
- **`MCPAuthorizationManager::auth_mutex_ → MCPKeySet::key_mutex_`** is a real call chain through `has_access`, but the receiver was never verified. The index shows only one ordering, so I see no deadlock risk here.