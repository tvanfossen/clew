Several subsystems run on their own threads. Most are guarded by a mutex or atomic and a clear join or hand-off point. Two spots are not safe as written: a detached async worker that can outlive the handle, and a manual join in one poller that can call `std::terminate`.

**Threads outside the caller's**

| Thread | Where | What it does | What keeps it safe |
|---|---|---|---|
| HealthMonitor loop | `src/mcp/health_monitor.cpp:92`, `:137` | Pings and reconnects external MCP servers, calls `connect()` and `refresh_tools()` | `watched_mutex_` held while checking servers (`:142`). Results go to `event_queue_` under `event_mutex_` and are drained on the engine thread by `process_events()` (`:118`). `stop()` joins (`:102`). `unwatch()` takes the same mutex before `disconnect_external_server` erases the client (`server_manager.cpp:669-673`). |
| External bridge accept thread | `src/facade/external_bridge.cpp:796` | Accepts unix-socket clients, checks peer uid (`:929`) | `running_` atomic. `stop()` closes the listen fd and joins (`:826-834`). |
| Per-client serve threads | `external_bridge.cpp:945` | One thread per connected client | Each fd is tracked in `client_threads_` under `client_threads_mutex_`. `stop()` shuts down each fd and joins (`:840-851`). Finished threads are reaped (`:880`). |
| Detached async-ask worker | `external_bridge.cpp:1158-1222` (`.detach()`) | Runs `entropic_run` for `entropic.ask(async=true)` | `tasks_mutex_` guards the task registry, and the sentinel write happens under it. Subscriber fanout uses `subscribers_mutex_`. The run path skips `api_mutex` (gh#109, `entropic.cpp:1984`) so interrupt can get through. |
| Cancel poller threads | `inference_c_api.cpp:385` (RAII class, `:376-404`), `interface_factory.cpp:246`, `response_generator.cpp:413` | Poll an `int*` cancel flag every 10 ms and raise a `std::atomic<bool>` | Atomics for the flag. The caller joins before returning. |
| Stdio stderr forwarder, SSE reader | `src/mcp/transport_stdio.cpp:164`, `src/mcp/transport_sse.cpp:107` | Read child stderr, read SSE events | `io_mutex_` guards pipe I/O (`transport_stdio.cpp:244`). `cancel_flag_` is atomic. I did not read the SSE reader's locking in depth. |

**What the engine relies on across threads**

- **Interrupt and pause** are `std::atomic<bool>` (`engine.h:1415-1416`). `AgentEngine::interrupt()` (`engine.cpp:994`) is callable from any thread.
- **Mid-generation message queue**: `queue_mutex_` guards `user_message_queue_` and the capacity (`engine.cpp:3184-3246`).
- **Delegation callbacks**: `delegation_cb_mutex_` gives atomic snapshot-and-swap.
- **Handle API**: `HandleApiLock` (`engine_handle.h:157-182`) serializes most `entropic_*` calls on `api_mutex`. Streaming and run paths deliberately skip it.
- **External client**: `tools_mutex_` guards the tool cache (`external_client.cpp:68`, `:81`, `:151`). The health monitor's reconnect path and engine-thread `execute()` share the transport, and `io_mutex_` covers the stdio pipe.
- **Lock order**: `watched_mutex_` → `wake_mutex_`, and `tasks_mutex_` → `observer_gen_` (atomic generation counter that drops stale observer callbacks, `external_bridge.cpp:1075-1101`).

**Gaps I found**

1. **Use-after-free risk on destroy during an async ask.** `entropic_destroy` calls `external_bridge->stop()`, then `delete handle` (`entropic.cpp:1883-1904`). `stop()` joins the accept and client threads but not the detached async worker. It also never calls `entropic_interrupt` first. If an async `entropic.ask` is still inside `entropic_run(handle_)`, that worker dereferences a freed handle and a freed bridge (`this`, `tasks_mutex_`, `broadcast_notification`). Fix: track in-flight workers with a counter or a `std::thread` you join, and interrupt before stop.
2. **Doc contradicts the code.** `external_bridge.h:21-24` says `api_mutex` serializes engine access. The gh#109 run path bypasses it, so the doc is wrong about the actual safety model.
3. **`std::terminate` hazard in `iface_generate_with_cancel`.** The `poller` at `interface_factory.cpp:244-262` is a raw `std::thread` joined by hand. If `orchestrator->generate` throws, the joinable thread is destroyed and the process aborts. The `CancelFlagBridge` RAII class in `inference_c_api.cpp` already avoids this, so reuse it here.
4. **Long reconnects block the engine thread.** `HealthMonitor::monitor_loop` holds `watched_mutex_` across `check_server`, which calls blocking `connect()`. `unwatch()` on the engine thread (`disconnect_external_server`) can stall for the whole reconnect backoff. This is latency, not a data race.
5. **Benign lost wakeup.** `HealthMonitor::stop()` sets `running_` and notifies without holding `wake_mutex_`. The 500 ms `wait_for` bounds the delay, so this only costs shutdown latency.

I did not run the test suite or ThreadSanitizer, so these are read-only findings. Gap 1 is the one I would verify first with a destroy-during-async-ask test under TSan or ASan.