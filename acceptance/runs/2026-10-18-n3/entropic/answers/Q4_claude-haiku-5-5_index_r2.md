Five spawn sites are in the index, but grep finds more, and the detached async-ask worker is the one place where the safety story has a real gap.

**Threads outside the caller's**

| Thread | Spawned at | What it does | What keeps it safe |
|---|---|---|---|
| `ExternalBridge` accept loop | `src/facade/external_bridge.cpp:796` | Polls the listen socket with a 500 ms timeout, rejects peers whose uid doesn't match (`SO_PEERCRED`), and spawns one thread per client. | Polls with a timeout so `running_` is checked. Connection threads are tracked under `client_threads_mutex_`, reaped when finished, and joined in `stop()` after `shutdown(SHUT_RDWR)`. |
| Per-client serve thread | `external_bridge.cpp:945` | Serves one MCP client on its own fd. | Owns its fd; the fd is closed and set to -1 on exit. Log scope is propagated via `HandleLogScope`. |
| Detached async-ask worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Runs `entropic_run` for `entropic.ask` in the background. | `tasks_mutex_` guards `tasks_`, and the sentinel file is written under it before the progress notification. `cancel_inflight_async_tasks` (`:434`) interrupts and waits about 1 s, then bumps the observer generation so stale callbacks are dropped. |
| `HealthMonitor::monitor_loop` | `src/mcp/health_monitor.cpp:92` | Checks watched MCP servers every 500 ms. | `watched_mutex_` guards the map. `wake_cv_` with a `running_` predicate makes shutdown prompt. |
| Stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Drains child stderr. | `io_mutex_` on the transport. I did not trace its join path. |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads the SSE stream. | `pending_mutex_` on the transport. I did not trace its join path. |
| Response observer | `src/core/response_generator.cpp:413` | Mirrors the engine's interrupt flag into an `int` for the C ABI while generation runs. | Joined before return (`:429`). |
| Cancel pollers | `src/inference/inference_c_api.cpp:385` (`CancelFlagBridge`), `src/inference/interface_factory.cpp:246` | Bridge the C-ABI `int*` cancel flag to a `std::atomic<bool>`, polling every 10 ms. | Joined in the destructor or after `generate`. The `done` flag is atomic. |

**Index coverage gap.** `search(corpus='threads')` reports 5 spawn sites. Grepping `std::thread` finds 9 in `src/`. The index missed the per-client thread (`:945`), the detached async worker (`:1158`), the response observer (`:413`), and both cancel pollers (`:385`, `:246`). Those are the spawns most relevant to the concurrency question, so don't quote the index's count as the thread count.

**Gaps I'd flag**

1. **Detached async worker outlives the bridge.** The lambda at `external_bridge.cpp:1158` captures `this` and `handle_`. `stop()` (`:826`) and `~ExternalBridge` (`:612`) join accept and client threads but not these detached workers. If the bridge is destroyed while an async ask is running, the worker touches freed memory. The only protection is the caller invoking `context_clear` or cancelling first, and that wait is best-effort (about 1 s, and the code says so). I'd make the worker tracked and joined in `stop()`, or hold a shared-ownership token.

2. **Plain `int` cancel flag shared across threads.** The observer at `response_generator.cpp:416` writes `cancel_int` (a plain `int`) while the backend reads it through a pointer on another thread. The same pattern appears in the cancel poller at `inference_c_api.cpp:387` and `interface_factory.cpp:248`. That is a data race under the C++ memory model even if it works on x86. An `std::atomic<int>` behind the `int*` view, or `std::atomic_ref`, would fix it without changing the C ABI.

3. **Lock ordering is only partly verified.** `search(corpus='locks')` reports three nested pairs, with no reversed pair. All three have `resolved_sites=0`, so none is confirmed. The pairs are `auth_mutex_` → `key_mutex_` (`mcp_authorization.cpp:105`), `event_mutex_` → `adapter_mutex_` (`health_monitor.cpp:122`), and the test mock's `mu_` → `adapter_mutex_`.

I did not run tests or a sanitizer; these findings are from reading the code and the index.