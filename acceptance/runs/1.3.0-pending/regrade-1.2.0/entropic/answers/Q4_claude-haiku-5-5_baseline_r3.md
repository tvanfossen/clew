Several background threads run alongside the caller. Most are joined and mutex-guarded, but the async `entropic.ask` worker is detached and can outlive its bridge.

**Threads that run off the caller's thread**

| Thread | Where | Purpose | How it's made safe |
|---|---|---|---|
| Batch cancel poller | `src/inference/interface_factory.cpp:244-262`, `src/core/response_generator.cpp:409-429`, `CancelFlagBridge` in `src/inference/inference_c_api.cpp:376-420` | Polls an `int*` cancel flag every 10 ms and raises an `std::atomic<bool>` for the backend | Stop flag is `std::atomic<bool>`, and the thread is joined before the function returns or in the destructor (RAII). |
| MCP accept loop | `src/facade/external_bridge.cpp:796` | Accepts socket clients | `running_` is atomic; `stop()` closes the listen fd, then joins. |
| Per-client serve threads | `src/facade/external_bridge.cpp:945` | One thread per connected client | Tracked in `client_threads_` under `client_threads_mutex_`; `stop()` calls `shutdown(fd)` to unblock reads, then joins. Finished threads are reaped. |
| Async `entropic.ask` worker | `src/facade/external_bridge.cpp:1158-1222`, `.detach()` | Runs `entropic_run` in the background | Task state is under `tasks_mutex_`. The sentinel is written under the same lock. Logs are scoped with `HandleLogScope`. |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Polls MCP servers every 500 ms and reconnects | `watched_mutex_` guards the watch list, `event_mutex_` guards the queue, and a `wake_cv_` wakes it on stop. Callbacks run on the engine thread via `process_events()`, not on the monitor thread. |
| Stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Forwards child stderr | `io_mutex_` guards pipe I/O. The `connected_` flag is atomic. |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads server-sent events | `pending_mutex_` guards pending responses. `connected_` and `running_` are atomic. |

**What keeps it safe**

- **Explicit locking:** each shared structure has a named mutex (`tasks_mutex_`, `client_threads_mutex_`, `subscribers_mutex_`, `watched_mutex_`, `event_mutex_`, `pending_mutex_`, `io_mutex_`). This matches the architecture rule of atomics for state queries and mutexes for transitions.
- **Join-on-shutdown:** `ExternalBridge::stop()` and the health monitor's `stop()` join their threads. The bridge destructor calls `stop()`.
- **Stale-callback guard:** `observer_gen_` and `attached_gen_` discard phase-observer callbacks that fire after detach.
- **Engine-thread callbacks:** health events are queued and delivered on the engine thread, so consumer code never runs on the monitor thread.
- **Per-run ownership:** each async run owns its own `result_json`, and the cancel path only raises the interrupt flag.

**Gaps I found**

1. **Detached async worker can outlive the bridge.** The lambda at `external_bridge.cpp:1158` captures `this` and is detached. Neither `stop()` nor the destructor waits for it. `cancel_inflight_async_tasks()` (around line 420) waits at most about 1 s and then gives up. If the bridge or the engine handle is destroyed while a worker is still in `entropic_run` or broadcasting, that is a use-after-free. Fix: track workers and join them in `stop()`, or hold a `shared_ptr` to the bridge state.
2. **The cancel poller reads a caller-owned plain `int`.** Both pollers do `*cancel_flag != 0` on an `int*` that another thread writes, with no atomic or fence. That is a data race under the C++ memory model, even though it usually works on x86. The C ABI forces the `int*` shape, so the fix is to have the C side take an `std::atomic<int>*` or an atomic-compatible wrapper, or to document that the caller must write through an atomic.
3. **Not verified:** I did not check whether the SSE and stdio reader threads are joined on every close path. The destructor and `close()` paths should be read to confirm.