Ten first-party spawn sites run on their own threads, per the index. Most are shut down by a `stop`/`close` that joins them. The exception is the async-ask worker, which is detached and not joined on destroy.

| Thread (spawn site) | What it does | What keeps it safe |
|---|---|---|
| **ExternalBridge `accept_loop`** (`src/facade/external_bridge.cpp:796`) | Accepts MCP socket clients, polling with a 500 ms timeout. | `stop()` clears `running_`, closes the listen fd and joins the thread. Each accepted fd is checked with `SO_PEERCRED`, so cross-uid connections are closed before a thread is spawned. |
| **ExternalBridge per-client `serve_client`** (`:945`) | One thread per connected client, blocking on reads. | `client_threads_mutex_` guards the vector. `stop()` calls `shutdown(SHUT_RDWR)` to unblock reads, then joins. `reap_finished_clients_locked()` joins and erases finished threads. |
| **ExternalBridge async ask `run_async_ask`** (`:1158`, detached at `:1222`) | Runs `entropic_run` on the handle in a fire-and-forget thread, then broadcasts `notifications/progress`. | `tasks_mutex_` guards the task registry, and the sentinel is written under that lock. The worker captures `this` and `handle_`. **See gap below.** |
| **HealthMonitor `monitor_loop`** (`src/mcp/health_monitor.cpp:92`) | Health and reconnect loop. | `stop()` sets `running_` false, notifies `wake_cv_`, and joins. Shared state is under `event_mutex_`, `watched_mutex_` and `wake_mutex_`. |
| **StdioTransport `stderr_reader_loop`** (`src/mcp/transport_stdio.cpp:164`) | Drains the child's stderr. | `close()` joins it (`transport_stdio.cpp:219`). I/O is serialized by `io_mutex_`. |
| **SSETransport `sse_reader_loop`** (`src/mcp/transport_sse.cpp:107`) | Reads the SSE stream. | `close()` clears `running_` and `connected_`, calls `client_->stop()`, notifies `pending_cv_`, then joins (`transport_sse.cpp:139`). Pending requests are under `pending_mutex_`. |
| **Cancel pollers**: `iface_generate_with_cancel` (`src/inference/interface_factory.cpp:246`), `CancelFlagBridge` (`src/inference/inference_c_api.cpp:385`), and the observer in `ResponseGenerator::dispatch_batch_generate` (`src/core/response_generator.cpp:413`) | Short-lived 10 ms polls that mirror an interrupt flag into the C-ABI `int` cancel flag. | The thread is joined before the call returns (`interface_factory.cpp:262`, `response_generator.cpp:429`, `inference_c_api.cpp:403`). Cross-thread flags are `std::atomic` with acquire/release ordering. The by-reference captures are safe only because of that join. |

Test-only spawns (`MockSSEServer`, `listen_after_bind`) are excluded.

**Gap: the detached async-ask worker.** I found no mechanism that waits for it:
- `ExternalBridge::stop()` does not track or join async workers.
- `~ExternalBridge` just calls `stop()`.
- `entropic_destroy` (`src/facade/entropic.cpp:1877`) stops the bridge, then does `delete handle` at `:1904`.
- `cancel_inflight_async_tasks` runs only from `handle_clear` (`external_bridge.cpp:459`), not on destroy.

So if a `entropic.ask` is in flight when the handle is destroyed, the detached worker can call `entropic_run(handle_)` and touch `this` and `tasks_` after they are freed. That is a use-after-free. I did not run it, so this is from reading the code. Fix options: keep a per-bridge count of in-flight workers and wait for it to reach zero in `stop()` (after cancelling via `entropic_interrupt`), or hold the worker threads in a joinable list like the client threads.

**Lock ordering.** The index shows three two-lock nestings: `event_mutex_` then `adapter_mutex_` in `HealthMonitor::process_events`, `auth_mutex_` then `key_mutex_` in `MCPAuthorizationManager::check_access`, and a test-only `mu_` then `adapter_mutex_`. I saw no opposite-order pair, so there is no deadlock pattern in the index. The index marks all three as having unverified receivers, so I would not claim the ordering is confirmed without checking those call sites.