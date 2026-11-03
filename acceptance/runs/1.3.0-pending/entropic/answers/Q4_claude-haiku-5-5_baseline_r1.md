Several parts of entropic run on their own threads. Most are joined before their owner returns, but the detached async-ask worker is not, and that is a real lifetime gap.

**Threads and what keeps each one safe**

| Thread | Where | Shared state and protection |
|---|---|---|
| MCP accept loop | `src/facade/external_bridge.cpp:796` | `running_` is atomic. Client thread list is guarded by `client_threads_mutex_`. Joined in `ExternalBridge::stop()`. |
| Per-client MCP serve threads | `external_bridge.cpp:945` | Each has its own fd. Tasks and subscribers use `tasks_mutex_` and `subscribers_mutex_`. `stop()` shuts down each fd to unblock `read()`, then joins. |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Task registry under `tasks_mutex_`. Phase observer is protected by a generation counter (`observer_gen_`, `attached_gen_`) so stale callbacks are ignored. Not joined by anyone (see below). |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Events go through `event_mutex_` and a queue. Callbacks run on the engine thread via `process_events()`. Joined in `stop()`. |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Uses `running_` and `connected_` flags. I did not check whether they are atomic. |
| Stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Joined on close. |
| Inference cancel pollers | `src/inference/inference_c_api.cpp:385`, `interface_factory.cpp:246`, `src/core/response_generator.cpp:413` | Short-lived, joined before the function returns. Stop flag is an `std::atomic<bool>` or a `done` flag. |

Across the whole engine, the main safety mechanisms are:

- **Per-handle serialization.** `engine_handle.h:76` has `api_mutex`. The RAII guard at `engine_handle.h:157-180` takes it together with the per-thread log scope. Engine calls are serialized, and the design doc says so for `engine.h:160` and `entropic.h:901`.
- **Atomics for state, mutexes for transitions.** This follows the architecture rule (`docs/architecture-cpp.md`, design rule 10).
- **Deterministic shutdown order.** `stop()` closes the listen fd, joins the accept thread, shuts down client fds, then joins client threads. `entropic_destroy` (`src/facade/entropic.cpp:1877-1886`) stops the bridge before the handle is torn down, because the bridge holds a raw pointer to it.
- **Thread-local log routing.** `HandleLogScope` (gh#59) is installed at the top of every spawned thread body so logs reach the owning handle's session log.
- **Cancel on context clear.** `cancel_inflight_async_tasks` (`external_bridge.cpp:434`) interrupts the engine and waits up to about 1 s for tasks to acknowledge cancel.

**Gaps I found while reading**

1. **Detached async worker outlives its owner.** The worker at `external_bridge.cpp:1158` captures `this` and `handle_`, then calls `entropic_run`, `update_task_phase`, and `broadcast_notification`. `ExternalBridge::stop()` never waits for it, and `entropic_destroy` does not cancel it before tearing down the handle. If the handle is destroyed while an ask is running, the worker dereferences freed memory. I did not reproduce this at runtime. The lifetime invariant is not enforced in code. A backlog proposal already flags the same detached-thread pattern (`.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md`).
2. **Plain `int` shared across threads.** In `response_generator.cpp:410-420`, the observer thread writes a non-atomic `cancel_int`. The pollers in `inference_c_api.cpp` and `interface_factory.cpp` read it through an `int*`. That is a data race under the C++ memory model, even if it is benign in practice. The fix is to make the cancel word an `std::atomic<int>`, or to pass an atomic flag across the boundary.

Suggested next steps: join or drain in-flight async workers in `stop()` or `entropic_destroy` (or track them in a counter that `stop()` waits on), and change the cancel int to an atomic. Neither change touches the interface headers.