The index shows **10 first-party spawn sites**. They fall into four groups, and most of the safety comes from a small set of mutexes and atomics plus join or detach discipline. The index's spawn detection is pattern-based (medium confidence), so a spawn primitive it does not recognise would not appear here.

**Threads running off the caller's thread**

| Thread | Spawned at | What it does | What keeps it safe |
|---|---|---|---|
| Async ask worker | `external_bridge.cpp:1158` in `ExternalBridge::run_async_ask` | Runs `entropic_run` for a background `entropic.ask` | Task map and sentinel writes are under `tasks_mutex_`. The thread is `.detach()`ed, so nothing joins it. Its only shared outputs are the task map and a broadcast. |
| Accept loop | `external_bridge.cpp:796` in `ExternalBridge::start` | Polls the listen socket every 500 ms | `running_` is an atomic checked each iteration. Each accepted fd is checked with `SO_PEERCRED` before a thread is spawned. |
| Per-client serve thread | `external_bridge.cpp:945` in `accept_loop` | Serves one MCP client | Owned by a `ClientThread` in `client_threads_`, guarded by `client_threads_mutex_`. It closes its own fd and sets `finished`. `reap_finished_clients_locked()` joins and erases them. |
| Health monitor | `health_monitor.cpp:92` in `HealthMonitor::start` | Background health loop | `process_events()` swaps the event queue out under `event_mutex_` and invokes callbacks after releasing the lock. The docstring says callbacks run on the engine thread. |
| Stdio stderr reader | `transport_stdio.cpp:164` | Reads the child's stderr | `io_mutex_` guards I/O on the transport. |
| SSE reader | `transport_sse.cpp:107` in `SSETransport::open` | Reads the SSE stream | `pending_mutex_` guards the pending-request map. |
| Cancel poller (C API) | `inference_c_api.cpp:385` in `CancelFlagBridge` | Mirrors an `int` cancel flag into an atomic | `done_` and `cancel_` are atomics with acquire/release ordering. The thread is joined in the destructor. |
| Cancel poller (factory) | `interface_factory.cpp:246` in `iface_generate_with_cancel` | Same bridge for the batch path | `std::atomic` `done` and `cancel_flag`, joined before return. |
| Batch observer | `response_generator.cpp:413` in `dispatch_batch_generate` | Mirrors the engine's `interrupt_flag_` into the C-ABI `int` | `observer_done` is an atomic. The thread is joined before the function returns. The `int` keeps atomics off the `.so` boundary, as the architecture requires. |

**What keeps them safe, in general**

- **Shared state is behind named mutexes.** The index lists 45 first-party lock identities. The ones that matter for threading are `tasks_mutex_`, `client_threads_mutex_`, `event_mutex_`, `io_mutex_` and `pending_mutex_`. Critical sections are RAII (`std::lock_guard`).
- **Cross-thread flags are atomics** with explicit acquire/release. The C ABI never exposes an `std::atomic`; it passes a plain `int*`, and the bridges above convert between the two.
- **Lifetime is handled by join or detach.** Pollers and observers are joined before their captured references go out of scope. Async workers and client threads are detached or reaped, and they close their own fds.
- **Ordering is explicit.** The sentinel file is written under `tasks_mutex_` before the progress notification goes out, so an external reader that reacts to the sentinel sees the same terminal state.
- **Security and logging context are propagated.** `SO_PEERCRED` gates accepted sockets. `HandleLogScope` carries the owning handle's log id into each new thread.

**Caveats**

- The lock-nesting data is weak. The index reports three two-lock pairs, but every one has `resolved_sites=0`, so none is confirmed. The one involving `event_mutex_` and `adapter_mutex_` in `process_events` looks like a match on the name `swap`, not a real nesting, because `process_events` releases its lock before running callbacks. I found no opposite-order pair, so no deadlock risk is confirmed.
- The index does not show the threads inside `entropic_run` or the inference backends, because they are not spawn sites in the first-party code that matched the patterns.
- `run_async_ask` is documented as a detached background thread, and its body shows `.detach()`. Its failure path is not verified: if `entropic_run` throws, `derive_async_final_state` and the sentinel write would not run.