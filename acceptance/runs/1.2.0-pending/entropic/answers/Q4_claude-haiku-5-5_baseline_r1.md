## Threads outside the caller's

| Thread | Where | Lifetime | Protection |
|---|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Per bridge, joined in `stop()` | `running_` atomic, `listen_fd_` closed to unblock |
| Per-client serve thread | `external_bridge.cpp:945` | Per connection, reaped or joined in `stop()` | `client_threads_mutex_`, `finished` flag, `shutdown()` to wake blocking reads |
| Async-ask worker (runs `entropic_run`) | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Detached, one per `entropic.ask` | `tasks_mutex_`, `subscribers_mutex_`, `api_mutex` |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Joined in `stop()` | `watched_mutex_`, `event_mutex_`, `wake_cv_` |
| Stdio stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Joined on close | `io_mutex_` |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Joined on close | `pending_mutex_` |
| Cancel pollers (3 places) | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` | Scoped to one generate call, joined before return | `std::atomic` done/cancel flags |

## What keeps it safe

- **Engine serialization.** Each handle has an `api_mutex` (`src/facade/engine_handle.h:76`). The async worker's `entropic_run` takes it, so it cannot race other API calls on the same engine. Long turns are the exception: several `entropic.cpp` entry points deliberately skip the lock (gh#109).
- **Shared state behind mutexes.** The task registry, subscriber set, client-thread vector, and health-monitor queues each have their own mutex, and the code documents which lock guards which field.
- **Atomics for flags.** `running_`, the cancel flags, and the `done` flags are atomics. Cross-thread cancellation goes through the atomic, not the raw `int*`.
- **Stale-callback guard.** `attach_phase_observer` and `detach_phase_observer` bump `observer_gen_`, so `phase_observer_cb` drops callbacks that fire after detach (`external_bridge.cpp:1091-1130`).
- **Ordered shutdown.** `ExternalBridge::stop()` closes the listener, joins the accept thread, shuts down each client fd, then joins the client threads (`external_bridge.cpp:826-890`).
- **Log context.** `HandleLogScope` is installed at the top of each thread body, so logs go to the owning handle's session log.

## Gaps I found

1. **Detached async worker can outlive the bridge and the handle.** This is the most serious one. The worker captures `this` and `handle_`. `ExternalBridge::stop()` and `~ExternalBridge()` do not wait for or cancel these workers. `entropic_destroy` calls `stop()` and then `delete handle` (`src/facade/entropic.cpp:1884-1904`). If an ask is in flight at that point, the worker can take `tasks_mutex_` or `api_mutex` on freed memory. The only cancel path is `cancel_inflight_async_tasks`, which runs on `context_clear` and polls for at most about 1 s (`external_bridge.cpp:434-460`). The backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` already describes this (unbounded detached threads) and plans a tracked executor. It is not implemented. I did not run a test to reproduce the use-after-free.

2. **Batch cancel poller is not exception-safe (plausible, not confirmed).** In `iface_generate_with_cancel` (`src/inference/interface_factory.cpp:234-266`), `poller` is a joinable `std::thread` with no RAII guard. If `ctx->orchestrator->generate(...)` throws, unwinding destroys a joinable thread and calls `std::terminate`. I did not confirm that `generate` can throw. The other two poller sites are safe because their join runs with no throwing call in between, or the call that sits in between is a C-ABI call.

The fix for gap 1 is to track async workers and join or cancel them in `stop()`, which is what the backlog item proposes. The fix for gap 2 is a small RAII joiner.