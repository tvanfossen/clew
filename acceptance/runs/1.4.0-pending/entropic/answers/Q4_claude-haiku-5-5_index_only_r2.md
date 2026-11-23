The index shows 10 thread spawn sites in entropic's own code, and none come from vendored code. Safety comes from three things: each background thread has a single owner that joins it, state is handed across threads under a named mutex, and cancellation is a polled flag. Two spots look weaker than the rest.

**Background threads and what keeps each safe**

| Thread (spawn site) | Role | Safety mechanism |
|---|---|---|
| `ExternalBridge::accept_loop` (`src/facade/external_bridge.cpp:796`) | Accepts MCP socket clients | Polls with a 500 ms timeout and checks `running_`. Rejects non-matching UIDs via `SO_PEERCRED` before spawning. Handed-off `client_threads_` are guarded by `client_threads_mutex_`. |
| Per-client `serve_client` thread (`external_bridge.cpp:945`) | Serves one client | Joined by `reap_finished_clients_locked()` once `finished` is set, and by `stop()`. `stop()` drains the list under the mutex, then joins outside it. |
| `ExternalBridge::run_async_ask` worker (`external_bridge.cpp:1158`) | Runs `entropic_run` for `entropic.ask` | Task registry writes are under `tasks_mutex_`. The terminal status and sentinel file are written together under that lock, so an external watcher sees a consistent pair. |
| `HealthMonitor::monitor_loop` (`src/mcp/health_monitor.cpp:92`) | Health checks and reconnects | Events are queued under `event_mutex_`. `process_events()` swaps the queue out and runs callbacks on the engine thread, so callbacks never run on the monitor thread. `stop()` sets `running_`, notifies the condition variable, and joins. |
| `StdioTransport::stderr_reader_loop` (`src/mcp/transport_stdio.cpp:164`) | Drains child stderr | `close()` closes the fds and then joins the thread. |
| `SSETransport::sse_reader_loop` (`src/mcp/transport_sse.cpp:107`) | Reads the SSE stream | `close()` sets `running_` false, notifies `pending_cv_` to wake waiters, and joins. |
| `dispatch_batch_generate` observer (`src/core/response_generator.cpp:413`) | Mirrors the engine's `interrupt_flag_` into an int cancel flag | Created per call and joined before return. The `observer_done` atomic ends its loop. |
| `iface_generate_with_cancel` poller (`src/inference/interface_factory.cpp:246`) and `CancelFlagBridge` poller (`src/inference/inference_c_api.cpp:385`) | Bridge the cancel flag into the backend | Joined before return, and both use an `atomic<bool>` done flag. |

**Concerns I found in the index**

1. **Plain `int` cancel flags are a data race.** The observer in `response_generator.cpp` writes `cancel_int = 1` on one thread while the backend reads it on another. `iface_generate_with_cancel` and `CancelFlagBridge` poll a plain `int*` the same way. The code comments say this keeps the C ABI `int*`-only. Under the C++ memory model, a non-atomic read/write across threads is undefined behaviour, even if it works on x86. The fix is an atomic type on both sides of the boundary, such as `_Atomic int` in C or `std::atomic_ref<int>` in C++.

2. **`ExternalBridge::stop()` may not wait for ask workers.** `stop()` joins the accept thread and the per-client threads. It does not track the `run_async_ask` workers. The index shows that worker as a bare `std::thread` lambda that captures `this` and `handle_`. The displayed part of its body does not show a `detach()`, and I could not read the tail (it was truncated at line 1201). If that thread is detached, destroying the bridge while an ask is running would leave it using a freed `this`. This needs confirmation by reading the rest of `run_async_ask`.

3. **Unsynchronised fd read in `stop()`.** The serve thread closes `raw->fd` and then sets it to `-1`. `stop()` reads `ct->fd` without a lock to call `shutdown()`. That is a data race, and if the fd number has been reused, `shutdown()` could hit the wrong socket.

I did not verify the lock-ordering nestings. The index reports three two-lock pairs, including `event_mutex_` → `adapter_mutex_` in `process_events`. All three have `resolved_sites=0`, so they are unconfirmed, and no deadlock cycle was found. Tests were not run; this is from reading indexed bodies only.