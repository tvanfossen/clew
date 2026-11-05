Several parts of entropic run on their own threads. Most are guarded by RAII joins, mutexes, or atomics. The one real hazard I found is in the detached async-ask workers.

| Thread | Where | Lifetime | Shared with | Protection |
|---|---|---|---|---|
| Cancel poller (`CancelFlagBridge`) | `src/inference/inference_c_api.cpp:385` | Per batch call | Caller's `int*` cancel flag, backend's `std::atomic<bool>` | RAII: destructor sets `done_` and joins. Cross-thread data is atomic only. |
| Cancel poller (inline) | `src/inference/interface_factory.cpp:246` | Per `iface_generate_with_cancel` call | Stack atomics, caller's `int*` | Joined explicitly after `generate()` returns. Lambda captures by reference, which is safe only because of that join. |
| Interrupt observer | `src/core/response_generator.cpp:413` | Per batch generation | `events_.interrupt` (atomic), local `cancel_int` | Joined after `generate_cancellable`. Same reference-capture pattern. |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Started/stopped with the server manager | `watched_`, `event_queue_` | `watched_mutex_` and `event_mutex_`, `wake_cv_` for shutdown. The monitor thread only queues events. `process_events()` drains them and runs the callbacks on the engine thread. |
| Stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Per open child process | Child's stderr fd | Mutex and join were not checked in this pass. |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Per SSE connection | `pending_mutex_`, `pending_cv_`, atomics `running_`/`connected_` | `close()` clears the flags, notifies the CV, and joins. |
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Bridge `start()` to `stop()` | Listen socket, client list | `stop()` closes the listen fd and joins the accept thread. |
| Per-client serve thread | `src/facade/external_bridge.cpp:945` | One per connected client | `client_threads_` under `client_threads_mutex_` | `stop()` drains the list, calls `shutdown(SHUT_RDWR)` to wake blocked reads, then joins. Finished threads are reaped. |
| Async `entropic.ask` worker | `src/facade/external_bridge.cpp:1158` | Detached | `tasks_` under `tasks_mutex_`, the handle, and the bridge `this` | Mutex-guarded task registry. Sentinel written under the lock. Observer generation counter discards stale callbacks. |

**What keeps it safe**

- **Joins on every path, RAII where possible.** The batch cancel pollers and the health monitor are joined before their captured stack state goes away. `CancelFlagBridge` is the cleanest version of this.
- **Atomics for flags, mutexes for transitions.** This matches the project's standard. Interrupt, cancel and status flags are atomic. Registries and queues are mutex-guarded.
- **No API lock on the run path.** `entropic_run` and `entropic_interrupt` deliberately avoid `api_mutex` (gh#109), so an interrupt from another thread can reach a running turn. The engine's interrupt and queue primitives are documented thread-safe.
- **Callbacks stay on the engine thread.** Health events are queued and drained on the engine thread rather than invoked from the monitor thread.
- **Per-thread log scope.** Each spawned thread installs a `HandleLogScope` so logs route to the owning handle.
- **Socket ownership.** `s_bound_sockets` stops two handles in one process from binding the same socket path.
- **Teardown order.** `entropic_destroy` stops the external bridge before deleting the handle, because the bridge holds a raw pointer to it.

**Gaps I found**

1. **Detached async workers can outlive the handle.** The worker in `run_async_ask` captures `this` (the bridge) and `handle_`, and calls `entropic_run(handle_, ...)`. It is detached and not tracked. `ExternalBridge::stop()` drains only the client threads. `entropic_destroy` calls `stop()` and then deletes the handle, and I found no wait for async workers on that path. The only cancel-and-wait for in-flight asks is `cancel_inflight_async_tasks`, which runs on `entropic.context_clear`. The header comment says "best-effort" and "detached workers may still be in flight." If a consumer destroys the handle while an async ask is running, the worker can use freed memory. I did not reproduce this.
2. **Exception safety of the join pattern.** In `iface_generate_with_cancel` and in the response-generator observer, the join runs only after the wrapped call returns normally. If `orchestrator->generate` or `generate_cancellable` throws, the joinable `std::thread` is destroyed and the process calls `std::terminate`. `CancelFlagBridge` avoids this. The other two should use the same RAII pattern. I did not confirm that these calls can throw.

If you want, I can fix gap 2 by moving the poller into a small RAII guard, and look at gap 1 by tracking async workers and joining them in `stop()` or `entropic_destroy`.