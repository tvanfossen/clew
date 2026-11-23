Entropic runs work on about a dozen background threads. Most follow a join-on-stop pattern with mutex-guarded state, but the detached async-ask worker is a real gap in its shutdown ordering.

## Threads that run off the caller's thread

| Thread | Where | What it does | How it hands back |
|---|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Polls the Unix socket every 500 ms, checks `SO_PEERCRED` uid, spawns a client thread per connection | Joined in `stop()` |
| Per-client serve threads | `external_bridge.cpp:945` | Reads JSON-RPC from one client and dispatches it | `stop()` calls `shutdown(SHUT_RDWR)` to wake reads, then joins. `reap_finished_clients_locked()` reclaims finished ones |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Runs `entropic_run` for `async=true` calls | Writes under `tasks_mutex_`, then broadcasts a notification. **Never joined** |
| Stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Drains MCP child-process stderr | Joined in transport teardown |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads the server-sent event stream and resolves pending JSON-RPC responses | Joined; responses handed over via `pending_mutex_` + `pending_cv_` |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Detects connection loss and schedules reconnects | Pushes events to a queue. `process_events()` runs callbacks on the engine thread |
| Cancel poller (backend) | `src/inference/inference_c_api.cpp:385` | Converts the C-ABI `int*` cancel flag into an `atomic<bool>` every 10 ms | Joined in the RAII destructor |
| Cancel poller (interface) | `src/inference/interface_factory.cpp:246` | Same pattern for the interface layer | Joined before return |
| Interrupt observer | `src/core/response_generator.cpp:413` | Watches the engine's interrupt flag during generation | Joined before return |

## What keeps it safe

- **Ownership and joins.** Every long-lived thread is a member joined in `stop()` or a destructor. `entropic_destroy` stops the bridge before deleting the handle (`src/facade/entropic.cpp:1883-1886`).
- **Mutex-guarded shared state.** The bridge has separate locks for `tasks_`, `subscribers_`, and `client_threads_`. Transports use `io_mutex_` for pipe I/O and `pending_mutex_` for responses. The health monitor uses `watched_mutex_` and `event_mutex_`.
- **Generation counter for stale observers.** `observer_gen_` (`external_bridge.cpp:1099-1127`) lets `phase_observer_cb` discard callbacks that fire after `detach_phase_observer()`.
- **Atomics for flags.** `running_`, `connected_`, `finished`, `done_`, and the cancel flag are `std::atomic`. The `finished` flag is set by the thread itself before exit, so reaping never blocks.
- **Event queue instead of cross-thread callbacks.** Health events are queued, and the engine thread drains them. Callbacks never run on the monitor thread.
- **Per-thread logging scope.** `HandleLogScope` (`include/entropic/types/logging.h:154`) is re-entered on each spawned thread so log lines route to the owning handle.
- **Socket claim registry.** `s_bound_sockets` (`external_bridge.cpp:770`) stops two handles in one process from binding the same path.
- **Cancel-before-clear.** `handle_clear` interrupts and waits up to about 1 s for in-flight async tasks before `entropic_context_clear` (`external_bridge.cpp:434-443`).

## Gaps

1. **Detached async worker outlives its owner (highest risk).** The worker captures `this` (the bridge) and `handle_`. `~ExternalBridge` only calls `stop()`, which does not wait for detached workers. `entropic_destroy` then deletes the handle at `entropic.cpp:1904`. If an `async=true` ask is still running at that point, the worker can touch freed memory. The fix is a counter of in-flight workers that `stop()` waits on, or a join-able `std::thread` in a task pool. A backlog proposal (`.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md`) already calls out the detach-per-task design as unbounded, but I did not see it name this shutdown race. I found this by reading the code and did not reproduce it.
2. **Plain `int` shared across threads.** `response_generator.cpp:416` writes `cancel_int` from the observer thread. `CancelFlagBridge` reads it through `*cancel_flag` on another thread. Neither side uses an atomic, so this is a data race even though the bytes are only ever 0 or 1. Making it an `std::atomic<int>` at the C ABI boundary, or passing the `atomic<bool>` through, would fix it.
3. **No test covers the detached-worker teardown.** The concurrency tests in `tests/concurrency/test_thread_safety.cpp` and the external-bridge tests do not appear to exercise destroying a handle mid-async-ask. I did not run any tests or a ThreadSanitizer build.