Nine spawn sites in `src/` run on a thread other than the caller's. A tenth, in a test mock, is out of scope. The index found them by matching spawn primitives, so a spawn written with a different primitive would not appear.

**Threads outside the caller's**

| Thread | Spawned in | What it does | How it ends |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` | Polls the listen socket, rejects other UIDs via `SO_PEERCRED`, spawns a serve thread per client | `running_` flag, joined in stop (`external_bridge.cpp:833`) |
| Per-client serve thread | `accept_loop` | Serves one MCP client | Joined on stop and reaped (`:850`, `:884`) |
| Async-ask worker | `ExternalBridge::run_async_ask` (`:1142`) | Runs `entropic_run` for `entropic.ask` | **Detached** (`:1222`) |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` | Periodically checks MCP servers | `running_` plus condvar, joined (`health_monitor.cpp:108`) |
| `SSETransport::sse_reader_loop` | `SSETransport::open` | Reads the SSE stream | Joined (`transport_sse.cpp:139`) |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` | Drains child stderr | Joined (`transport_stdio.cpp:219`) |
| Cancel poller | `CancelFlagBridge` (`inference_c_api.cpp:385`) | Polls an `int*` cancel flag every 10 ms | Joined in destructor |
| Cancel poller | `iface_generate_with_cancel` (`interface_factory.cpp:246`) | Same, for the batch path | Joined before return |
| Interrupt observer | `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`) | Mirrors the engine's `interrupt_flag_` into the C-ABI `int` | Joined before return |

**What keeps them safe**

- **Shared state is behind named mutexes.** The async-task registry is guarded by `ExternalBridge::tasks_mutex_`, client threads by `client_threads_mutex_`, subscribers by `subscribers_mutex_`. The health monitor uses `watched_mutex_` and `wake_mutex_`. The stdio and SSE transports use `io_mutex_` and `pending_mutex_`.
- **Terminal state is written under the lock.** In `run_async_ask`, the sentinel file is written while `tasks_mutex_` is held, before the completion notification goes out. An external monitor that reacts to the sentinel will see the same state that `entropic.ask_status` returns.
- **Cancellation uses atomics and polling.** `running_`, `done`, and `cancel_flag` are atomics. Pollers wake every 10 ms and exit when `done` is set. Each short-lived poller is joined before its caller returns, so its by-reference captures stay valid.
- **Logging scope crosses the boundary.** Each spawned lambda re-enters `HandleLogScope(log_id)`, so its logs route to the owning handle's session log.
- **Lock order.** The index reports no opposite-order lock pairs. It shows `auth_mutex_`→`key_mutex_` (4 sites), and `event_mutex_`→`adapter_mutex_` in `HealthMonitor::process_events`. Three pairs have no verified receivers, so treat them as unconfirmed.

**Gaps to check**

1. **The detached async-ask thread captures `this` and `handle_`, and nothing joins it.** `ExternalBridge` has no in-flight counter. `cancel_inflight_async_tasks` (`external_bridge.cpp:434`) only signals cancellation and waits up to about 1 s (20 × 50 ms) for tasks to report cancelling. If the bridge is destroyed while a worker is still running, the worker dereferences freed memory. I did not verify what the destructor does here. This is the most important thing to check.
2. **`dispatch_batch_generate` shares a plain `int`.** `cancel_int` is written by the observer thread and read by the backend's poller, with no atomic. That is a data race under the C++ memory model, even if it is benign on current targets. Changing it to `std::atomic<int>` would require a C-ABI change, which is why the code uses the `int` (see the comment at `response_generator.cpp:403`). A safer fix is to keep the `int` at the C boundary and have the observer write an atomic that the bridge copies from.