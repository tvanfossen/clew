Entropic has about a dozen background threads in the C++ engine. Most are created and joined by their owner, and shared state is guarded by mutexes or atomics. One path is detached and is not covered by that discipline.

**Threads that run off the caller's thread**

| Where | Thread | Lifetime | Synchronization |
|---|---|---|---|
| `src/facade/external_bridge.cpp:796` | Accept loop for the external MCP Unix socket | Joined in `stop()` | `running_` atomic; listen fd closed to unblock accept |
| `external_bridge.cpp:945` | One serve thread per connected client | Tracked in `client_threads_`; reaped when finished, and `stop()` does `shutdown(fd)` then join | `client_threads_mutex_`; `finished` atomic |
| `external_bridge.cpp:1158` | Async `entropic.ask` worker | **Detached** | `tasks_mutex_` for `tasks_`, observer generation, and the sentinel write |
| `src/mcp/transport_stdio.cpp:164` | Child-process stderr forwarder | Joined in `close()` | `connected_` atomic; `io_mutex_` for pipe I/O |
| `src/mcp/transport_sse.cpp:107` | SSE event reader | Joined in `close()` | `connected_`/`running_` atomics; `pending_mutex_` |
| `src/mcp/health_monitor.cpp:92` | Health monitor loop | Joined in `stop()` | `watched_mutex_`, `event_mutex_`, `wake_mutex_`; events are drained on the engine thread via `process_events()` |
| `src/inference/inference_c_api.cpp:385` | Cancel poller that bridges `int*` to `atomic<bool>` | Joined in `CancelFlagBridge` destructor | Atomics only |
| `src/inference/interface_factory.cpp:246` | Same cancel bridge for batch generate | Joined before the function returns | Atomics; `done` flag |
| `src/core/response_generator.cpp:413` | Interrupt observer | Joined before the function returns | Atomics; the `&cancel_int` capture is safe because of the join |

**What keeps it safe**

- **Ownership and join discipline.** Every joinable thread has a single owner that joins it in `stop()`, `close()`, or the destructor. The short-lived pollers join before their stack-captured references go out of scope.
- **Cross-thread flags are atomics.** `running_`, `connected_`, `done`, and the cancel flags use acquire/release atomics, which matches the design rule "`std::atomic` for state queries, mutex for transitions only."
- **Shared registries have named mutexes.** Each guarded member has a comment naming its mutex, for example `tasks_mutex_` and `subscribers_mutex_`.
- **Blocked reads are woken before joining.** `stop()` calls `shutdown(SHUT_RDWR)` on client fds, closes the listen fd, and joins the accept thread, so no thread can hang the join.
- **The C ABI stays pointer-only.** Cancel crosses the `.so` boundary as `int*`, and the atomic is kept inside the library, per design rule 1 and rule 6 (no exceptions across the boundary).
- **Stale callbacks are discarded.** The phase observer compares `observer_gen_` with `attached_gen_` under `tasks_mutex_`, so a callback from a detached worker cannot update a later task.

**The gap: the detached async-ask worker**

- `run_async_ask` launches `std::thread([this, ...]{...}).detach()` (`external_bridge.cpp:1158–1222`). The thread captures `this`, then touches `tasks_`, `write_sentinel`, `broadcast_notification`, and `cleanup_expired_tasks` after `entropic_run` returns.
- `ExternalBridge::stop()` (`external_bridge.cpp:826`) does not wait for these workers. It only joins the accept thread and the client threads. The destructor just calls `stop()`. So if the bridge is destroyed while an ask is running, the worker can use a dead `this`.
- `cancel_inflight_async_tasks` only waits about 1 s, and only on `context_clear`, so it does not cover teardown either.
- The file `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` already records this as unbounded, with a proposed bounded task pool. I did not find a cap on accepted clients in the part of the accept loop I read.

I did not check whether engine teardown waits for `entropic_run` to return, which would make the `handle_` side safe even though the bridge side is not. A fix would track in-flight workers and join them in `stop()`, or move them onto a bridge-owned pool, as the backlog proposal describes.

Note: a hook suggested a `dossier` tool for this lookup. I don't have that tool in this session, so I used grep and sed.