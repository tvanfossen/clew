Several parts of entropic run off the caller's thread. Most are guarded by mutexes, atomics, and joins. The detached async-ask worker is the exception: nothing waits for it, so it can outlive the object it uses.

**Background threads**

| Where | Thread | Shared state and how it's guarded | Lifetime |
|---|---|---|---|
| `src/facade/external_bridge.cpp:796`, `include/entropic/mcp/external_bridge.h:387` | Accept loop | `running_` is atomic; the fd is closed in `stop()` | Joined in `stop()` |
| `external_bridge.cpp:945` | One thread per MCP client | `client_threads_` under `client_threads_mutex_`; `finished` is atomic | `stop()` shuts down each fd, then joins |
| `external_bridge.cpp:1158` | Async `entropic.ask` worker | `tasks_` under `tasks_mutex_`; subscribers under `subscribers_mutex_` | **Detached**; never joined |
| `src/mcp/health_monitor.cpp:92` | Health monitor loop | `watched_` and `event_queue_` each have a mutex; `running_` is atomic; a condvar wakes it | Joined in `stop()` |
| `src/mcp/transport_stdio.cpp:164` | Child-process stderr reader | `io_mutex_`; `connected_` is atomic | Owned by transport |
| `src/mcp/transport_sse.cpp:107` | SSE reader | `pending_mutex_` plus condvar; `running_` and `connected_` are atomic | Owned by transport |
| `src/core/response_generator.cpp:413` | Cancel observer per batch generate | Shares `cancel_int` and `observer_done` by reference | Joined before return |
| `src/inference/inference_c_api.cpp:385` | `CancelFlagBridge` poller | Atomics only; RAII joins in the destructor | Joined in destructor |
| `src/inference/interface_factory.cpp:246` | Cancel poller in the interface factory | Atomics plus by-reference locals | Joined before return |

**What keeps it safe**

- **Hand-off through the engine thread.** `HealthMonitor` worker threads only enqueue events. `process_events()` (called from `server_manager.cpp:710`) drains them and runs the callbacks on the engine thread.
- **Cancel pollers.** Each poller watches a flag every 10 ms and sets an atomic. Joining happens before the locals they reference go out of scope.
- **Per-handle logging.** Each spawned thread opens a `HandleLogScope` so its log lines reach the owning handle's session log (`include/entropic/types/logging.h:147`).
- **Socket ownership.** `s_bound_sockets` stops two handles in one process from binding the same socket path.
- **Teardown order.** `entropic_destroy` stops the external bridge before releasing the inference interface, since the interface context holds a raw orchestrator pointer (`src/facade/entropic.cpp:1883`).

**Gaps I found**

1. **Detached async worker outlives the bridge (most serious).** `run_async_ask` (`external_bridge.cpp:1158–1222`) captures `this` and `handle_`, then detaches. `stop()` joins only the accept and client threads (`external_bridge.cpp:826–851`; I did not read past line 851). The destructor and `entropic_destroy` call `stop()` and do not wait for running async tasks. `cancel_inflight_async_tasks` polls for at most about 1 s, and only runs from `context_clear`. So destroying a handle while an async ask is running can let the worker call `entropic_run` on a freed handle and touch the freed bridge's mutexes and registry. The comment at line 323 admits detached workers "may still be in flight". I have not reproduced this.

2. **Exceptions can terminate the process.** In `response_generator.cpp:413` and `interface_factory.cpp:246`, the thread is joined by hand after the generate call. Nothing wraps that call in a try, so if it throws, the joinable `std::thread` destructor calls `std::terminate`. `CancelFlagBridge` avoids this because RAII joins it.

**Suggested fixes**

- Track in-flight async workers with a counter or a set of futures, and have `stop()` cancel them and wait with a deadline. Better, use a `std::jthread` or join in `stop()`, instead of `detach()`.
- Put the generate calls in the two manual-join sites behind an RAII guard like `CancelFlagBridge`.