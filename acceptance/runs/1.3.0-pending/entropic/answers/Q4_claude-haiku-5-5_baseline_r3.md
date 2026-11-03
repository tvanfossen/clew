Several parts of entropic run on their own threads. Most are guarded by atomics, scoped mutexes and join-before-return discipline. Two spots look unsafe, and I did not run the tests or ThreadSanitizer to confirm either one.

**Threads outside the caller's**

| Thread | Where | Lifetime |
|---|---|---|
| External MCP accept loop | `src/facade/external_bridge.cpp:796` | Joined in `stop()` |
| Per-client serve threads | `external_bridge.cpp:945` | Shut down via `shutdown(SHUT_RDWR)` and joined in `stop()` |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | Detached, never joined |
| HealthMonitor loop | `src/mcp/health_monitor.cpp:92` | Joined in `stop()` |
| Stdio stderr reader | `src/mcp/transport_stdio.cpp:164` | Joined in `close` |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Joined in `close` |
| Cancel pollers (10 ms) | `response_generator.cpp:413`, `inference_c_api.cpp:385`, `interface_factory.cpp:246` | Joined before the call returns |

**What keeps them safe**

- **Atomics for flags:** `running_`, `connected_`, `interrupt_flag_`, `pause_flag_`, `observer_gen_` and the cancel flags are atomic. `interrupt()` is callable from any thread.
- **Scoped mutexes:** `tasks_mutex_`, `client_threads_mutex_`, `subscribers_mutex_`, `watched_mutex_` and `write_mutex_` (audit logger) each guard one structure.
- **Callbacks on the engine thread:** HealthMonitor queues events under `event_mutex_` and runs the status callback only from `process_events()`, so callers never see a callback on the monitor thread (`health_monitor.cpp:118`).
- **Stale-callback rejection:** the phase observer compares `observer_gen_` with `attached_gen_` and drops callbacks that fire after detach (`external_bridge.cpp:1072-1127`).
- **Ordered shutdown:** `ExternalBridge::stop()` stops accepting, shuts down client sockets to unblock reads, then joins (`external_bridge.cpp:826-851`).
- **Per-thread log routing:** each spawned thread installs `HandleLogScope` so its logs reach the owning handle's session log (gh#59).
- **Sentinel write ordering:** the async result and sentinel file are written under `tasks_mutex_` before the completion notification goes out (`external_bridge.cpp:1171-1183`).

**Gaps**

1. **Detached async worker outlives its owner.** The worker captures `this` and `handle_`. `stop()` and `~ExternalBridge` do not wait for it, and nothing counts in-flight workers. The header only says the handle must outlive the bridge. If the bridge is destroyed while a task runs, the worker's `tasks_mutex_` lock and `broadcast_notification` touch freed memory. `cancel_inflight_async_tasks` only polls for about 1 s (`external_bridge.cpp:439`) before continuing.

2. **Engine state is touched unlocked during a run.** The run path deliberately skips `api_mutex` (`src/facade/entropic.cpp:1984`, gh#109). `clear_conversation()` mutates `conversation_` with no lock (`src/core/engine.cpp:3152`). `handle_clear` (`external_bridge.cpp:457-460`) calls it after the 1 s wait, so if `run_turn` is still in progress, the two race on `conversation_`. I am inferring this from the code; a test or TSan run would settle it.

The fix for the first gap is to track in-flight workers with a counter or a join list and wait for them in `stop()`. For the second, `handle_clear` should wait for the run to finish, or the engine should guard `conversation_` with a mutex.