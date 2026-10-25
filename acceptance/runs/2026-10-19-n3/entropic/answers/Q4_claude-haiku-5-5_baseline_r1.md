Several threads run outside the caller's, and the safety comes from a few mechanisms: per-handle mutexes, atomics for cross-thread flags, mutex-guarded queues, and join-on-stop. One spot looks unsafe on shutdown.

**Threads that run off the caller's thread**

| Thread | Where | What it does |
|---|---|---|
| ExternalBridge accept thread | `src/facade/external_bridge.cpp:796` | Polls the listen socket, checks peer uid, spawns a client thread per connection |
| ExternalBridge per-client threads | `external_bridge.cpp:945` | Serve one MCP client each |
| Async-ask worker (detached) | `external_bridge.cpp:1158-1222` | Runs `entropic_run` for `entropic.ask`, then broadcasts `notifications/progress` |
| HealthMonitor loop | `src/mcp/health_monitor.cpp:92` | Checks server liveness every 500 ms and reconnects |
| Stdio stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Forwards MCP server stderr |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Reads server-sent events; has a condition variable for response arrival |
| Cancel pollers (short-lived) | `src/inference/inference_c_api.cpp:385`, `src/inference/interface_factory.cpp:246`, `src/core/response_generator.cpp:413` | Mirror an `int*` cancel flag into a `std::atomic<bool>` every 10 ms |

**What keeps them safe**

1. **Per-handle serialization.** `engine_handle.h:172` defines `HandleApiLock`, which takes `handle->api_mutex` and sets a log scope. Facade calls take this lock. `entropic_run` is the exception: it sets only the log scope (`entropic.cpp:1984`, gh#109), so a long turn doesn't block `entropic_interrupt()`.
2. **Lock-free queueing for mid-run input.** `entropic_queue_user_message` (`entropic.cpp:2630`) takes no `api_mutex`. It relies on the engine's own queue mutex, so it can't deadlock against a running turn.
3. **Atomics for cross-thread flags.** `running_`, `observer_gen_`, `connected_` and the cancel flags are `std::atomic`. Reads are lock-free, and the architecture doc (`docs/architecture-cpp.md:458`) says the same: `state_` is atomic, and `transition_mutex_` guards transitions only.
4. **Mutex-guarded shared state.** The bridge has `tasks_mutex_`, `subscribers_mutex_` (so concurrent broadcasts don't interleave on one fd) and `client_threads_mutex_`. The health monitor has `watched_mutex_` and `event_mutex_`.
5. **Callbacks marshalled to the engine thread.** The health monitor's `post_event` only queues events. `process_events()` (`health_monitor.cpp:118`), called from `server_manager.cpp:710`, runs the user callback on the engine thread.
6. **Stale-callback guard.** `observer_gen_` vs `attached_gen_` makes a phase-observer callback that fires after detach exit without touching state.
7. **Joined helper threads.** The cancel pollers are joined before their captured locals go out of scope, so the by-reference captures stay valid.
8. **Ordered shutdown.** `ExternalBridge::stop()` (`external_bridge.cpp:826`) sets `running_` false, closes the listen fd, joins the accept thread, `shutdown()`s each client fd to wake blocked reads, and joins each client thread. It also erases the socket path and its process-registry entry. Finished client threads are reaped so the vector doesn't grow.

**The gap I found**

The async-ask worker is `.detach()`ed (`external_bridge.cpp:1222`). Its lambda captures `this` and `handle_`. `stop()` and the destructor join only the accept and client threads. I found no counter, future or join for in-flight async tasks. So if the bridge is destroyed while `entropic_run` is still going, the worker can touch freed memory. `cancel_inflight_async_tasks` (line 434) only signals interrupt and waits at most 1 s, so it doesn't close the gap. The lifetime of `handle_` relative to the bridge is also not visible from this code. This is the same concern the backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` raises about unbounded `detach()` threads. I did not run anything, so this is from reading the code. A test that destroys the bridge during an in-flight ask would confirm it.