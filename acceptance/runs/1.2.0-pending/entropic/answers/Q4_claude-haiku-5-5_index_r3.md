Ten thread spawn sites in first-party code (the index's exact count for the patterns it searches). They fall into three groups: long-lived background loops, short-lived helper threads that exist only for one call, and a detached worker. The main safety mechanisms are a mutex on each shared structure, an atomic flag or `poll` timeout to stop loops, and a few per-handle or per-process guards. One real gap is the detached async-ask thread.

**1. Long-lived background threads**

| Thread | Spawned at | What it does | Protection |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` in `start()` | Polls the listen socket every 500 ms, checks peer uid, spawns one serve thread per client | `running_` atomic; `poll()` timeout; `client_threads_mutex_` around the vector push and reap |
| Per-client `serve_client` threads | `external_bridge.cpp:945` in `accept_loop` | Read requests from one MCP client | Each has its own fd, closed by the thread on exit; `stop()` moves the list out under `client_threads_mutex_`, then `shutdown(SHUT_RDWR)`s each fd and joins |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` in `start()` | Health pings and reconnect backoff for MCP servers | Events go through `event_queue_` under `event_mutex_`; `process_events()` swaps the queue out and runs the callbacks on the engine thread |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` in `open()` | Drains child-process stderr | `io_mutex_` on the transport |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` in `open()` | Reads the SSE stream | `pending_mutex_` on the transport |

The engine thread never calls into the health-monitor loop directly. It only drains the queue, so callbacks always run on the caller's side.

**2. Short-lived helper threads (one per call)**

These are joined before the function returns, so they are bounded by the call itself:

- `iface_generate_with_cancel` (`interface_factory.cpp:246`) starts a poller that turns the C `int*` cancel flag into an `atomic<bool>`, polling every 10 ms. The poller is joined after `orchestrator->generate` returns.
- `CancelFlagBridge` (`inference_c_api.cpp:385`) is the same pattern for the C API. Its destructor stops the poller.
- `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`) starts an observer that mirrors the engine's `interrupt_flag_` into the cancel int. It is joined after the call. Speculative decoding skips this path entirely (gh#110).
- Test-only: `MockSSEServer::listen_after_bind`.

Cancellation is safe here because each poller reads a flag and writes only its own atomic or int. The `done` flag is released before `join()`, so the poller always exits.

**3. Detached worker: `ExternalBridge::run_async_ask`**

`run_async_ask` (`external_bridge.cpp:1142`, `.detach()` at line 1222) runs `entropic_run` on a detached thread for an `entropic.ask` call. Its safety rests on:

- `tasks_mutex_` guards the `tasks_` map. The terminal status and the sentinel file are written under the same lock (issue #12), so an external reader cannot see a result before its sentinel exists.
- Log routing uses `HandleLogScope(log_id)` captured by value at spawn time.
- The broadcast uses `send(MSG_DONTWAIT | MSG_NOSIGNAL)`, so a slow subscriber cannot stall the worker. `broadcast_notification` also snapshots the subscriber set under `subscribers_mutex_` and writes outside the lock.

**The gap:** the worker captures `this` and `handle_`, but it is detached. `ExternalBridge::stop()` (`external_bridge.cpp:826`) joins the accept thread and the client threads and then returns. It does not wait for in-flight async tasks. I found no in-flight counter (grepped `src/facade` for `in_flight`, `active_async`, `async_count`, `outstanding`, `pending_async`). If the handle is destroyed while an ask is running, the worker can dereference a dead `this` or `handle_`. I did not verify this with a test. The fix would be a counter or a join list for async workers, drained in `stop()`.

**Lock-ordering notes**

- The index reports one nesting that needs checking: `HealthMonitor::event_mutex_` taken before `AdapterManager::adapter_mutex_` in `process_events` (`health_monitor.cpp:122`). It has zero resolved call sites, so I cannot confirm it from the index. I also did not check whether any path takes the two locks in the reverse order, so no deadlock claim is made.
- `auth_mutex_` → `key_mutex_` in `check_access` (`mcp_authorization.cpp:105`) has four sites. None are resolved, so this is unverified too.