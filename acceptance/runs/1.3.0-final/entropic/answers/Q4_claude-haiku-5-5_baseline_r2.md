Several parts of entropic run off the caller's thread. Most of them are guarded by mutexes and atomics, but the detached async-ask worker has a lifetime gap on handle destruction.

**Background threads found**

| Thread | Where | What keeps it safe |
|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Lifetime is tied to `running_` (atomic) and joined in `stop()`. |
| Per-client MCP serve threads | `external_bridge.cpp:945`, reaped in `reap_finished_clients_locked()` (`:880`) | Each has its own `finished` atomic. `stop()` (`:826`) moves the list out under `client_threads_mutex_`, `shutdown()`s each fd to unblock reads, then joins. |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Task map and sentinel writes under `tasks_mutex_`; notifications go through `subscribers_mutex_`. **Gap below.** |
| Phase observer callback | `external_bridge.cpp:1072`, fired from the engine | `observer_gen_` (atomic, bumped under `tasks_mutex_`) discards stale callbacks after detach. |
| Cancel pollers (`int*` → atomic) | `src/inference/inference_c_api.cpp:385`, `src/inference/interface_factory.cpp:246`, `src/core/response_generator.cpp:413` | Joined by RAII or explicitly before the enclosing scope ends. Captured references stay valid because of that join. |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Checks run on the monitor thread under `watched_mutex_`. Events go into `event_queue_` under `event_mutex_`, and callbacks run on the engine thread via `process_events()` (`:118`, called from `server_manager.cpp:710`). `stop()` uses `wake_cv_` to wake and join. |
| MCP transports | `transport_stdio.cpp:164` (stderr), `transport_sse.cpp:107` (SSE reader) | Use `io_mutex_`, `pending_mutex_`/`pending_cv_`, and atomics (`connected_`, `running_`). I did not read these in depth. |

**The gap: detached async worker vs. handle destruction**

- `entropic_destroy()` (`src/facade/entropic.cpp:1885`) calls `external_bridge->stop()` and then frees the handle.
- `stop()` (`external_bridge.cpp:826`) joins the accept thread and client threads. It does not track or join the detached async-ask threads, and it does not interrupt them.
- The only cancel path is `cancel_inflight_async_tasks()` (`:434`), which runs on `entropy.context_clear`, not on destroy.
- So if an async ask is still inside `entropic_run(handle_, ...)` when the caller destroys the handle, the detached thread can keep using `handle_` and `this` after they are freed. The worker then calls `update_task_phase`, `write_sentinel`, and `broadcast_notification` on a dead bridge.

I inferred this from reading the code. I did not reproduce it. The fix would be a counter or condition variable for in-flight async workers, with `stop()` interrupting and waiting for them to drain before the bridge and handle are torn down. Replacing the detach with a tracked `std::thread` (the P2-20260429-001 backlog proposal) would do the same.

**Smaller caveat**

The `int` cancel flag is written by one thread and read by another without `std::atomic` (`response_generator.cpp:416`, and the poller in `interface_factory.cpp:248`). This is a technical data race. The C ABI deliberately uses `int*` to avoid crossing atomics at the `.so` boundary. The practical risk is low, but a `std::atomic_ref` or a relaxed atomic on the shared int would make it well-defined.

**Bottom line:** the design is mostly sound. Joined helper threads, mutex-guarded registries, generation-counted observers, and the engine-thread drain of health events are all solid. The async-ask detached worker is not covered by the destroy path, and that is the main safety concern to fix.