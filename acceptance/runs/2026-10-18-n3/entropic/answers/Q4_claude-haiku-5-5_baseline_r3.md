Several parts of entropic run off the caller's thread. The safety comes from mutexes, atomics, and joins, with one real gap in the async-ask path.

**Background threads (all `std::thread`, as found by grep)**

| Thread | Where | Lifetime / sync |
|---|---|---|
| Accept loop | `src/facade/external_bridge.cpp:796` | Joined in `stop()` |
| Per-client serve thread | `external_bridge.cpp:945` | Stored in `client_threads_` under `client_threads_mutex_`; shut down and joined in `stop()` |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Detached, never joined |
| Health monitor loop | `src/mcp/health_monitor.cpp:92` | Joined in `stop()`; events cross to the engine thread via a queue |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Member thread, `close()` clears `running_` |
| Stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Member thread (teardown not checked) |
| Cancel pollers | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` | Short-lived, joined before the call returns |

**What keeps them safe**

- **Shared state is locked or atomic.** Bridge task registry and sentinel writes sit under `tasks_mutex_`. Client list sits under `client_threads_mutex_`. Health events go through `event_mutex_`, and `process_events()` swaps the queue out and runs callbacks on the engine thread. The engine's `interrupt_flag_` is an `std::atomic<bool>` (`engine.h:1415`).
- **Stale observer callbacks are fenced.** `attach_phase_observer` / `detach_phase_observer` bump `observer_gen_` under the lock, so a callback from a finished task is discarded.
- **Cancel pollers are joined.** The three poller sites capture locals by reference, which is only safe because they join before returning. `CancelFlagBridge` (`inference_c_api.cpp`) does this in its destructor (RAII).
- **Log routing across threads.** Each spawned thread installs a `HandleLogScope` with the owning handle's id, so log lines land in the right session log.
- **Shutdown ordering.** `ExternalBridge::stop()` closes the listen fd, joins the accept thread, shuts down client sockets to wake blocked reads, then joins the clients. `entropic_destroy` calls this before resetting the bridge.

**Gaps I found**

1. **Detached async workers can outlive the handle.** The worker captures `this` and calls `entropic_run(handle_, …)`. `stop()` does not wait for it. `entropic_destroy` tears the bridge down and then the handle, so a worker still running can touch freed memory. The only mitigation is `cancel_inflight_async_tasks`, which runs on `entropic.context_clear` and polls about 1 s. It is not called on stop or destroy. The code comment admits detached workers "may still be in flight". The backlog item `P2-20260429-001` already plans to replace this with a joinable executor pool.
2. **Poller threads are not exception-safe.** In `iface_generate_with_cancel` (`interface_factory.cpp`) and `ResponseGenerator`'s observer (`response_generator.cpp`), a `std::thread` is joined only on the normal return path. If `generate` throws, the joinable thread's destructor calls `std::terminate`. `CancelFlagBridge` avoids this; these two sites should use the same RAII pattern.
3. **SSE connect uses a fixed sleep.** `SSETransport::open` sleeps 500 ms and then reads `connected_`. That is a timing guess, not a handshake.

I didn't check the stdio stderr thread's teardown or whether `HealthMonitor`'s destructor calls `stop()`. A PostToolUse hook suggested a `dossier` tool; I don't have it, so I used grep and sed.