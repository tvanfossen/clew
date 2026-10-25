Several parts of entropic run off the caller's thread. Most are guarded by mutexes, atomics, or join-before-return. The one I'd call a real hazard is the detached async worker, which is not joined on shutdown.

## Threads that run off the caller's thread

| Thread | Where | What it does | What keeps it safe |
|---|---|---|---|
| Accept loop | `src/facade/external_bridge.cpp:796` | Polls the listen socket every 500 ms | `running_` is atomic. `stop()` closes the listen fd, then joins (`:826-834`). |
| Per-client serve threads | `external_bridge.cpp:945` | One per connected MCP client, blocked in `read()` | Accepted fds are gated by `SO_PEERCRED` (`:929`). `stop()` calls `shutdown(SHUT_RDWR)` on each fd to wake the read, then joins (`:846-851`). Finished threads are reaped under `client_threads_mutex_` (`:880`). |
| Async-ask worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Runs `entropic_run` for `entropic.ask` | Task registry is guarded by `tasks_mutex_`. The sentinel file is written under that lock (`:1183`). The phase observer uses a generation counter so stale callbacks are dropped (`:1076`, `:1120`). |
| Broadcast | `external_bridge.cpp:1285` | Sends notifications to subscribers from worker threads | Subscriber set is copied under `subscribers_mutex_`. Sends use `MSG_DONTWAIT \| MSG_NOSIGNAL`. Dead fds are dropped. |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Polls server liveness every 500 ms and attempts reconnects | Checks run under `watched_mutex_`. Events go into a queue under `event_mutex_` (`:291`). The engine thread drains the queue via `process_events()` (`server_manager.cpp:710`), so callbacks run on the engine thread, not the monitor thread. |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads the server-sent-event stream | `close()` sets flags, wakes waiters, and joins (`:127-140`). |
| Stdio stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Forwards subprocess stderr | Not read in detail. |
| Cancel poller (batch) | `src/inference/inference_c_api.cpp:376-420` | Polls an `int*` cancel flag every 10 ms and raises a `std::atomic<bool>` for the backend | RAII class. `done_` is atomic, and the destructor joins. |
| Cancel observer (response generator) | `src/core/response_generator.cpp:410-429` | Mirrors the engine interrupt flag into an `int` for the backend | Joined on every path before the locals go out of scope. |
| Interface-factory poller | `src/inference/interface_factory.cpp:244` | Similar cancel bridge | Not read in detail. |

The project's own rule in `.claude/CLAUDE.md` is "`std::atomic` for state queries, mutex for transitions only." The code follows it. Thread-local log routing is also propagated explicitly into each spawned thread via `HandleLogScope` (for example `external_bridge.cpp:797`, `:946`, `:1159`). Without that, log lines from the new threads would not reach the owning handle's session log.

## Hazards I found

1. **The detached async worker outlives the bridge.** `run_async_ask` captures `this` and detaches the thread. `stop()` and `~ExternalBridge` (`:612`) do not wait for in-flight async workers. The only wait is the roughly 1 s poll in `cancel_inflight_async_tasks` (`:439`), which is used by `context_clear`, not by teardown. If the bridge is destroyed while a run is in flight, the worker touches freed members, and the phase observer still registered on the handle may point at freed memory. I did not verify whether the handle always outlives the bridge in callers. The backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` already flags the unbounded detach and proposes a bounded worker pool. It does not appear to cover the teardown race.

2. **Non-atomic `int` cancel flag across threads.** The C ABI passes `int*`, and the observer thread (`response_generator.cpp:416`) writes it while the backend reads it. The poller in `inference_c_api.cpp` does the same. Under the C++ memory model this is a data race, even if it works in practice on current hardware. The `int*` shape is forced by the C ABI, but the reads and writes could use `std::atomic_ref` or relaxed atomic access.

3. **Health monitor holds one lock across slow work.** `check_server` and `attempt_reconnect` run under `watched_mutex_`, which `watch()` and `unwatch()` also take. A slow reconnect blocks unwatching. This is a latency issue, not a data race.

I did not run the concurrency tests in `tests/concurrency/test_thread_safety.cpp`, so the above comes from reading the code.