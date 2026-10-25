Entropic has five long-lived background threads that the index tracks, plus several short-lived helper threads it does not. Each one is either joined by its owner or guarded by a lock. One detached thread is the exception, and I could not confirm that it is safe.

**Tracked background threads (index `threads`)**

| Thread | Spawned in | Lifetime / teardown | Shared state and guard |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` (`start`) | Polls with a 500 ms timeout; `stop()` clears `running_`, closes the listen fd and joins it (`:832`) | Rejects peers whose uid doesn't match (`SO_PEERCRED`) before spawning a serve thread |
| Per-client `serve_client` threads | `external_bridge.cpp:945` | `stop()` drains `client_threads_` under `client_threads_mutex_`, calls `shutdown(SHUT_RDWR)` on each fd to unblock reads, then joins (`:840–850`) | `client_threads_mutex_` guards the vector; finished threads are reaped under the same lock |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Waits on `wake_cv_` with a 500 ms timeout; `stop()` joins (`:108`) | `watched_mutex_` around the watch table; `wake_mutex_` for the CV |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Exits when `connected_` clears; joined at `:219` | Read-only on its own fd; logs through the logger |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Exits when `running_` clears; joined at `:139` | `pending_mutex_` for pending requests; `connected_` and `running_` are atomics |

Across these, the pattern is: the owner stores the `std::thread`, sets an atomic `running_` flag, wakes or unblocks the thread (fd shutdown or CV notify), and joins in `stop()`/`close()`. Mutexes are used for state transitions, and atomics for flags that are read in loops. This matches the "atomic for state queries, mutex for transitions" rule in CLAUDE.md.

**Threads the index did not list**

The index only recognises the spawn patterns it was built with, so these `std::thread` sites are invisible to `search(corpus='threads')`. I found them with grep.

- **Async `entropic.ask` worker**, `external_bridge.cpp:1158`. It is a detached thread that calls `entropic_run` and writes the task result under `tasks_mutex_`, then broadcasts a progress notification. Safety comes from `tasks_mutex_` plus the `cancel_inflight_async_tasks` path, which is used by `context_clear` (`:434–443`).
- **Cancel-poller threads**, `inference_c_api.cpp:385`, `interface_factory.cpp:246` and `response_generator.cpp:413`. These poll a caller's `int*` or atomic flag every 10 ms and forward it to the backend's `std::atomic<bool>`. Each one is joined before its function returns, and the lambdas capture locals only by reference. That is safe because of the join. The `CancelFlagBridge` destructor (`inference_c_api.cpp:401–403`) does the same job.

**The open question**

The async-ask thread at `external_bridge.cpp:1158` is detached and captures `this`. `stop()` does not wait for it. I found no in-flight counter or join on that path, so if the bridge is destroyed while a task is still running, that thread could touch `tasks_mutex_`, `tasks_` and `broadcast_notification` on a freed object. I did not find a guard in the code I read. I did not check the `ExternalBridge` destructor, `handle` teardown or the `entropic_run` shutdown path, so I can't say whether something upstream prevents this. To settle it, read the destructor and the handle-destroy path, and check whether they call `cancel_inflight_async_tasks` and wait for `tasks_` to drain.

**Lock nesting**

The index reports 45 distinct lock identities in this repository and three two-lock nestings. None of the three is a reversed pair, so none is a deadlock risk on the index's evidence. Those three nestings also all rest on unverified receivers (`resolved_sites=0`), so treat them as unconfirmed.