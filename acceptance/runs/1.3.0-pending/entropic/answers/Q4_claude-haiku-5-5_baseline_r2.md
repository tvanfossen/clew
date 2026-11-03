Several threads run off the caller's thread, and most of them are guarded by mutexes, atomics, or joins. Two spots I checked don't hold up under the documented contract: nothing enforces one run per handle, and a detached async worker can outlive the bridge that owns it.

**Threads that run off the caller's thread**

| Thread | Where | What it does |
|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Accepts MCP client sockets |
| Per-client thread | `external_bridge.cpp:945` | Serves one client, owned by `client_threads_` |
| Detached async ask worker | `external_bridge.cpp:1158`, `.detach()` at 1222 | Runs `entropic_run` on the handle, then broadcasts progress |
| Cancel-flag poller | `src/inference/inference_c_api.cpp:385` | Bridges `int*` cancel to `std::atomic<bool>` at 10 ms |
| Generator observer | `src/core/response_generator.cpp:413` | Mirrors `interrupt_flag_` into the batch cancel int |
| Interface poller | `src/inference/interface_factory.cpp:246` | Same cancel bridging, for the interface path |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Polls MCP servers, queues events |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads the server-sent event stream |
| Stdio stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Forwards child stderr |

**What keeps it safe**

- **Documented per-handle contract.** `include/entropic/entropic.h:20` says calls are thread-safe, serialized per handle, or init/destroy only. The state-observer doc (line 469) says callbacks may fire from the async worker and must be thread-safe.
- **Lock split on the run path.** Most API calls take `HandleApiLock` (`src/facade/engine_handle.h:172`). `entropic_run` deliberately does not (gh#109), so `entropic_interrupt` from another thread doesn't block behind a long turn. Interrupt and pause are atomics (`engine.h:1415`).
- **Stale observer callbacks.** `attach_phase_observer` and `detach_phase_observer` bump `observer_gen_` under `tasks_mutex_`. `phase_observer_cb` compares generations and drops late callbacks (`external_bridge.cpp:1077–1124`).
- **Task state and sentinel.** Final task status and the sentinel file are written together under `tasks_mutex_` before the completion notification goes out (`external_bridge.cpp:1171–1183`).
- **Broadcast.** Subscribers are snapshotted under `subscribers_mutex_`, sends use `MSG_DONTWAIT | MSG_NOSIGNAL` without the lock held, and dead fds are pruned afterwards (`external_bridge.cpp:1285`).
- **Health events.** Monitor-thread events go into a queue under `event_mutex_`, and the callbacks run on the engine thread via `process_events()` (`health_monitor.cpp:118`).
- **Backend.** State is atomic. Load and unload take `transition_mutex_`, evaluation takes `eval_mutex_`, and generation runs concurrently with neither (`backend.h:11–17`).
- **Joins and RAII.** `CancelFlagBridge` joins in its destructor. `HealthMonitor::stop()` notifies and joins. `ExternalBridge::stop()` closes the listen socket, joins accept, shuts down client fds, then joins client threads. Log scope is propagated into each spawned thread (`HandleLogScope`).

**Gaps I found**

1. **Per-handle serialization is not enforced.** `entropic_run` takes no lock and never checks `running_flag_` (`src/facade/entropic.cpp:1974`). `AgentEngine::run_turn` sets the flag and doesn't check it first (`src/core/engine.cpp:2831`). `ENTROPIC_ERROR_ALREADY_RUNNING` is defined and documented in `entropic.h:267` and `:368`, but no code returns it. An async ask and a sync ask on the same handle can therefore enter `run_turn` at the same time, which the header says must not happen. I did not run this, and I did not read `run_drain_loop`, so I can't rule out a guard there.
2. **`running_flag_` is not exception-safe.** `run_turn` clears the flag only on normal return. If the drain loop throws, the flag stays true, and `queue_user_message` will keep accepting messages on an idle handle.
3. **Detached async workers can outlive the bridge.** The worker captures `this` and the handle. `stop()` joins only the accept and client threads, not the async workers. `entropic_destroy` calls `stop()` and then tears down the orchestrator (`entropic.cpp:1884–1894`). If an async ask is running at destroy time, the worker can touch freed memory. The only wait for in-flight workers is the best-effort ~1 s poll in the context-clear cancel path (`external_bridge.cpp:434–459`), which doesn't run on destroy. The backlog proposal `P2-20260429-001` already describes the unbounded detached threads.

Gaps 1 and 3 are the ones to confirm first. A test that starts an async ask, then calls a sync run or `entropic_destroy`, would show whether they're real. `tests/concurrency/test_thread_safety.cpp` exists, but I didn't read it, so I can't say whether it covers either case.