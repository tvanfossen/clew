Several parts of entropic run on their own threads. Most follow one pattern: a dedicated thread owns a loop, shared state sits behind a mutex or an atomic, and the owner joins the thread on stop or destruction. One place breaks that pattern: the async `entropic.ask` worker is detached, and I found nothing that waits for it on handle teardown.

**Long-lived worker threads**

| Thread | Where | What it does | How it stays safe |
|---|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Accepts MCP socket clients | `running_` atomic; `stop()` closes the listen fd, joins the thread, then joins client threads |
| Per-client serve thread | `external_bridge.cpp:945` | Serves one connected client | `client_threads_mutex_`; `stop()` calls `shutdown(SHUT_RDWR)` to unblock reads, then joins |
| Health monitor | `src/mcp/health_monitor.cpp:92` | Polls MCP servers, reconnects with backoff | `watched_mutex_` around the watch table; `wake_cv_` for prompt stop; `stop()` joins. Status events go through `event_mutex_` and are delivered via `process_events()` on the engine thread |
| Stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Forwards child stderr | `close()` terminates the child, closes fds, then joins; `io_mutex_` guards the pipe I/O |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads server-sent events | `pending_mutex_` + `pending_cv_` hand responses back; `close()` stops the client and joins |
| Inference cancel poller | `src/inference/inference_c_api.cpp:385` | Bridges an `int*` cancel flag to an atomic | Atomic `done_`; destructor joins |

**Short-lived helper threads**

These are created per call and joined before the call returns. They capture locals by reference, which is only safe because of that join:

- `src/inference/interface_factory.cpp:246`: cancel poller for `iface_generate_with_cancel`.
- `src/core/response_generator.cpp:413`: interrupt observer for the streaming path.

**The async `entropic.ask` worker (the exception)**

- `run_async_ask` (`external_bridge.cpp:1158`) starts `std::thread(...).detach()`. The worker captures `this` and calls `entropic_run(handle_, ...)`.
- `ExternalBridge::stop()` (`external_bridge.cpp:820`) does not touch `tasks_` and does not wait for these workers.
- `entropic_destroy` (`src/facade/entropic.cpp:1883`) calls `stop()`, then `delete handle`.
- The only wait is `cancel_inflight_async_tasks` (`external_bridge.cpp:434`), which is called from `context_clear`. It polls for about 1 s and then gives up.

So if a handle is destroyed while an async ask is still inside `entropic_run`, the worker keeps running against a freed bridge and a freed handle. I read the code but did not reproduce this. The backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` already calls out the detached-thread pattern as a known concurrency hazard. The fix is to track the workers and join them in `stop()`, or to hold a shared-ownership reference in the worker.

**What keeps the rest safe**

- **Mutexes on shared registries:** `tasks_mutex_`, `subscribers_mutex_`, `client_threads_mutex_`, `watched_mutex_`, `event_mutex_`, `io_mutex_`, `pending_mutex_`. `CLAUDE.md` says mutexes are for transitions only and atomics are for state queries.
- **Atomics for flags:** `running_`, `connected_`, `done_`, cancel flags. These are read on each loop iteration.
- **Ordered teardown:** `stop()` and `close()` flip the flag, wake or unblock the thread, then join. Client threads are drained by moving them out under the lock and joining outside it.
- **Observer generation:** `observer_gen_` lets callbacks from a detached observer be discarded after detach (E5+E6 in `external_bridge.cpp`).
- **Terminal sentinel under lock:** `write_sentinel` runs under `tasks_mutex_` before the completion notification fires.
- **Log routing:** every spawned thread installs a `HandleLogScope` so its logs reach the owning handle's session log.
- **No API mutex on `entropic_run`:** gh#109 removed the per-handle `api_mutex` from run paths so `entropic_interrupt()` can be called from another thread during a long turn. This means the engine's own internal guarding is what keeps concurrent calls safe. I did not audit that path.

**Not verified**

- `HealthMonitor::set_status_callback` writes `status_callback_` without a lock. That is only safe if it is always called before `start()`. I did not check the call sites.