Several parts of entropic run on their own threads. Most are joined before their owner returns, and the one detached worker has no join at all.

| Thread | Where | Lifetime | What keeps it safe |
|---|---|---|---|
| External MCP accept loop | `src/facade/external_bridge.cpp:796` | Started in `start()`, joined in `stop()` | `running_` is atomic; `client_threads_` is guarded by `client_threads_mutex_`; the accept loop checks `SO_PEERCRED` before spawning anything |
| Per-client serve threads | `external_bridge.cpp:945` | One per accepted socket; reaped by `reap_finished_clients_locked()` | `stop()` moves the list out under the mutex, calls `shutdown(SHUT_RDWR)` to wake blocking reads, then joins each thread |
| Async ask worker (`entropic.ask`) | `external_bridge.cpp:1158`, `.detach()` at 1222 | Detached, runs `entropic_run` for the task | Task map is guarded by `tasks_mutex_`; the sentinel is written under that lock; subscribers are guarded by `subscribers_mutex_` |
| Cancel poller (batch) | `src/inference/interface_factory.cpp:244-262` | Joined before the function returns | `std::atomic<bool>` for `cancel_flag` and `done`; captures by reference are safe because of the join |
| Cancel poller (`CancelFlagBridge`) | `src/inference/inference_c_api.cpp:376-420` | Joined in the destructor | Atomics with release/acquire ordering; the `int*` is polled, so no atomic crosses the `.so` boundary |
| Interrupt observer | `src/core/response_generator.cpp:410-430` | Joined before return | Same pattern as above; `interrupt_flag_` is an atomic on the engine |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Started in `start()`, joined in `stop()` | `watched_mutex_` covers the watch map; `event_mutex_` guards the queue, which is swapped out and drained on the caller's thread; `wake_cv_` lets `stop()` wake it immediately |
| Stdio transport stderr reader | `src/mcp/transport_stdio.cpp:164` | Started in `open()` | Reads from a pipe fd the transport owns |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Started in `open()` | `running_` and `connected_` are atomic |

Cross-cutting safety mechanisms:

- **Per-handle API lock.** Facade entry points take `HandleApiLock` (`src/facade/engine_handle.h:172`), which acquires `api_mutex` and installs the per-handle log scope. The log scope is thread-local, so logs from a worker thread still route to the right session.
- **Interrupt and pause are atomics.** `AgentEngine::interrupt()` uses `exchange(true)` (`src/core/engine.cpp:995`), so a Ctrl+C or an external thread can raise it without taking the API lock.
- **Callbacks are marshalled back.** The health monitor queues events and delivers them on the caller's thread via `process_events()`, so user callbacks do not run on the monitor thread.
- **Lock ordering is documented in code.** `HandleApiLock` takes `api_mutex` before the log scope and releases in reverse.

The open risk is the detached async-ask thread. The lambda captures `this` (the `ExternalBridge`) and `handle_`, and `stop()` does not wait for it, so the bridge or the engine handle could be destroyed while `entropic_run` is still executing. I did not confirm whether `entropic_run` takes `HandleApiLock`, or whether the bridge destructor waits for outstanding tasks. The existing backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` already describes the unbounded `std::thread(...).detach()` pattern as a known issue. I'd treat that as the first thing to verify before relying on the async path during shutdown.