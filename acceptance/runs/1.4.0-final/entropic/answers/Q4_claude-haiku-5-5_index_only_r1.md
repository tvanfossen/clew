Ten thread spawn sites in the repo, and most of the runtime ones are background workers that share state through mutexes, atomics, or a join before return. I could not inspect every worker body, so some safety claims below rest on what the index recorded.

**Threads that run off the caller's thread (runtime)**

| Thread | Spawned in | What it does | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` (`src/facade/external_bridge.cpp:796`) | Polls the listen socket, accepts clients | Polls with a 500 ms timeout so it can see shutdown. Drops clients whose uid fails the `SO_PEERCRED` check before any thread is spawned. Pushes into `client_threads_` under `client_threads_mutex_` and reaps finished threads. |
| Per-client `serve_client` thread | Inside `accept_loop` (`:945`) | Serves one MCP client | Owns its fd and closes it on exit. `stop()` calls `shutdown(fd, SHUT_RDWR)` to unblock reads. Logs are scoped to the owning handle via `HandleLogScope`. |
| `ExternalBridge::run_async_ask` worker | `run_async_ask` (`:1158`) | Runs `entropic_run` for an async ask in a detached thread | Task state is written under `tasks_mutex_`. The sentinel file is written under that same lock before the progress notification goes out, so a watcher that reacts to the sentinel sees the same terminal state. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` (`src/mcp/health_monitor.cpp:92`) | Background health checks | Events are queued under `event_mutex_`. `process_events()` swaps the queue out under the lock, then runs callbacks on the engine thread with no lock held. |
| `SSETransport::sse_reader_loop` | `SSETransport::open` (`src/mcp/transport_sse.cpp:107`) | Reads the SSE stream | `running_` and `connected_` are atomics. `open()` waits 500 ms and then checks `connected_`, closing on failure. The pending-request map is guarded by `pending_mutex_`. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` (`:164`) | Drains the child's stderr | Writes to the child are serialised by `io_mutex_`. |
| Cancel poller threads | `iface_generate_with_cancel` (`src/inference/interface_factory.cpp:246`), `CancelFlagBridge` (`inference_c_api.cpp:385`) | Mirror an `int` cancel flag into an atomic for the backend, polling every 10 ms | Stop flag is an atomic (`done`). The thread is joined before the function returns, so it cannot outlive the stack data it captures. |
| Observer in `dispatch_batch_generate` | `ResponseGenerator::dispatch_batch_generate` (`src/core/response_generator.cpp:413`) | Copies the engine's `interrupt_flag_` into the C-ABI int cancel flag | `observer_done` is an atomic with release/acquire ordering. The thread is joined before return. |

**Things to check**

- **Plain `int` cancel flag.** In `dispatch_batch_generate`, the observer writes `cancel_int` as a plain `int`, and the backend poller reads it through `int*`. Only `observer_done` is atomic. The join keeps lifetimes safe, but the cross-thread access to `cancel_int` is a formal data race. Making it `std::atomic<int>`, or passing an atomic through the boundary, would remove it. I did not see this flagged anywhere in the index.
- **Lock ordering.** The index found three two-lock nestings, and none is taken in opposite orders, so no deadlock pair shows up. However, all three rest on receivers the index could not verify (`resolved_sites=0`). Treat "no deadlock risk" as unconfirmed for now.
- **Scope of the count.** The 10 sites come from the spawn patterns this build recognises (`ast_spawn`, medium confidence). Two of them (`MockSSEServer`, `transport_sse_test`) are test-only, so the runtime count is 8. Any spawn helper outside those patterns would not appear.

**Cross-cutting pattern.** The design keeps cross-thread state small. Shared data sits behind a named mutex (`tasks_mutex_`, `event_mutex_`, `client_threads_mutex_`, `io_mutex_`, `pending_mutex_`). Stop and cancel signals are atomics. Every helper thread is joined or closed before its owner returns, and callbacks run on the engine thread rather than on the worker.