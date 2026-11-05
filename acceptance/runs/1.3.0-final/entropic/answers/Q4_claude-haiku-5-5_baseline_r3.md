The engine runs work on several background threads. Most of them are guarded by mutexes, atomics, and join-on-stop, but one path can outlive its object.

**Background threads**

| Thread | Where | Shared state and guard |
|---|---|---|
| External MCP accept loop | `src/facade/external_bridge.cpp:796` | `running_` atomic; `s_bound_sockets_mu` for the socket registry. Peer UID is checked with SO_PEERCRED before a serve thread starts (line 929). |
| Per-client serve threads | `external_bridge.cpp:945` | `client_threads_mutex_` for the vector; per-thread `finished` atomic; `subscribers_mutex_` for the fd set. |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, **detached** | `tasks_mutex_` guards the task registry. The sentinel is written under that lock (line 1183). |
| Health monitor | `src/mcp/health_monitor.cpp:92` | `watched_mutex_` guards the watch map; `event_mutex_` guards the event queue. Callbacks are queued and run on the engine thread via `process_events()` (`server_manager.cpp:710`). |
| MCP stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Joined in `close()`. `io_mutex_` guards writes. |
| MCP SSE reader | `src/mcp/transport_sse.cpp:107` | Joined in `close()`. `pending_mutex_` correlates responses. |
| Short-lived cancel pollers | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` | Each is joined before the call returns. Each uses an atomic "done" flag. |

**What keeps them safe**

- **Engine flags are atomics.** `interrupt_flag_`, `pause_flag_` and `running_flag_` are `std::atomic` (`include/entropic/core/engine.h:1415-1446`). The header documents interrupt and pause as thread-safe.
- **The non-blocking run path takes no `api_mutex`.** The comments at `entropic.cpp:1984` and `2622` say this is deliberate (gh#109), so interrupt and queue calls can land during a long turn. Mid-generation queueing relies on the engine's own `queue_mutex_`.
- **Cross-thread callbacks are marshalled.** The health monitor queues events and the engine thread drains them. The async worker's state observer (`external_bridge.cpp:1072`) takes `tasks_mutex_` and uses a generation counter so stale callbacks are ignored.
- **Notifications don't block workers.** `broadcast_notification` sends with `MSG_DONTWAIT | MSG_NOSIGNAL` and drops slow or dead subscribers (line 1296), so one slow client can't stall the worker.
- **Shutdown is ordered.** `ExternalBridge::stop()` (`external_bridge.cpp:826`) clears `running_`, closes the listen fd, joins the accept thread, shuts down each client fd, and then joins the client threads. The stdio and SSE transports and the health monitor are joined on close or destruction.

**Hazards I found**

1. **Detached async worker can outlive the handle (likely use-after-free).** The worker captures `this` (the bridge) and `handle_`, and is started with `.detach()` at line 1222. Nothing tracks it. `stop()` does not cancel or wait for it. `entropic_destroy` (`entropic.cpp:1877-1904`) stops and resets the bridge, then runs `delete handle`. If an ask is still running, the worker then calls `entropic_run(handle_)`, `update_task_phase`, and `broadcast_notification` on freed memory. The backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` already describes the unbounded detached-thread pattern. I did not find a fix in the code. I haven't run this, so it is inferred from reading the code.
2. **The `int*` cancel flag is a plain data race.** The pollers read `*cancel` and the observer writes `cancel_int = 1` (`response_generator.cpp:416`) with no atomic. The C++ memory model makes this undefined behaviour even though it usually works. The fix is to make the flag `std::atomic<int>` or use `std::atomic_ref`.
3. **`HealthMonitor::status_callback_` is unguarded.** `set_status_callback` assigns it with no lock (`health_monitor.cpp:78`). This is only safe if it is set before `start()`.

I did not run the concurrency tests in `tests/concurrency/test_thread_safety.cpp`, so the claims about safety are from reading the code, not from test results.