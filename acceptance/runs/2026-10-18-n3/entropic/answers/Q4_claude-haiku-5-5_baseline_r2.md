Several parts of entropic run off the caller's thread. They fall into two groups: long-lived background threads that the owning object starts and joins, and short-lived per-operation threads. Safety comes from per-structure mutexes, atomics, and joins or event queues. I read the code but did not run the tests or a thread sanitizer, so the claims below are from reading.

**Background threads owned by an object**

| Thread | Where | Shared state and guard | Teardown |
|---|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | `running_` is atomic; `listen_fd_` | `stop()` closes the listen fd, then joins |
| External bridge per-client serve threads | `external_bridge.cpp:945` | `client_threads_` under `client_threads_mutex_`; `finished` is atomic | `stop()` calls `shutdown(fd)` to wake blocking reads, then joins; finished threads are reaped |
| Health monitor | `src/mcp/health_monitor.cpp:92` | `watched_` under `watched_mutex_`; event queue under `event_mutex_` (swapped out, then callbacks run) | `stop()` sets the flag, notifies the cv, joins |
| Stdio child stderr reader | `src/mcp/transport_stdio.cpp:164` | `io_mutex_` guards pipe I/O; `cancel_flag_` and `connected_` are atomic | joined on close |
| SSE reader | `src/mcp/transport_sse.cpp:107` | `pending_mutex_` guards pending responses; `connected_`, `running_`, `next_request_id_` are atomic | `close()` clears `running_`, then joins |

The health monitor's status callbacks are not invoked on the monitor thread. `process_events()` drains the queue and runs them on the engine thread, so the engine's own code never sees the monitor thread's state.

**Short-lived per-operation threads**

- **Response generator observer** (`src/core/response_generator.cpp:413`). A thread polls the engine's atomic interrupt flag every 10 ms and copies it into `cancel_int`. It is joined before `generate` returns, and `observer_done` is an atomic stop signal.
- **Cancel bridge** (`src/inference/inference_c_api.cpp:385`, `CancelFlagBridge`). An RAII poller translates a C-ABI `int*` cancel flag into `std::atomic<bool>` for the backend. The destructor sets `done_` and joins.
- **Orchestrator cancel poller** (`src/inference/interface_factory.cpp:246`). The same pattern as the bridge, scoped to one call and joined before returning.
- **Async ask worker** (`external_bridge.cpp:1158`, detached at `:1222`). This is the riskiest one, covered below.

**What keeps it safe**

1. **Named guards.** Headers state which mutex protects which member (for example `tasks_mutex_`, `subscribers_mutex_`, `client_threads_mutex_`).
2. **Snapshot, then send.** `broadcast_notification` copies the subscriber fds under the lock and does the non-blocking `send` (`MSG_DONTWAIT | MSG_NOSIGNAL`) outside it. Dead fds are removed in a second locked pass.
3. **Lock-ordering and state under lock.** The async worker writes the terminal status and the sentinel file under `tasks_mutex_` before it broadcasts, so a client that reacts to the notification sees the same state.
4. **Engine serialization.** `HandleGuard` in `src/facade/engine_handle.h` takes `api_mutex` and then the log scope. `entropic_run_streaming` and `entropic_run` are serialized per handle, which the bridge header relies on.
5. **Deliberately lock-free control calls.** `entropic_queue_user_message` (`entropic.cpp:~2622`) and the run-path log scopes do not take `api_mutex`, so a long turn cannot block `entropic_interrupt()` or message queuing. The engine's queue has its own mutex.
6. **Log context propagation.** Every spawned thread installs a `HandleLogScope` with the owning handle's `log_id` (gh#59), so logs from background threads land in the right session.
7. **Join or detach discipline.** Every owned thread is joined in `stop()` or the destructor, except the async workers, which are detached.

**Gaps I'd check before relying on this**

- **Detached async workers outlive their owner.** The worker captures `this` and is detached, so nothing I read waits for it. I did not verify whether `ExternalBridge`'s destructor or `stop()` waits for in-flight async tasks. If it does not, a worker finishing after destruction touches freed memory. The backlog proposal `P2-20260429-001` describes this as unbounded thread-per-task and does not reference a join.
- **Plain `int` shared across threads.** In the response generator and the cancel bridges, the observer or poller reads a plain `int` (`*cancel_flag`) that another thread writes, with no atomic or fence. The reads are technically a data race even though they are benign in practice. Making the C-ABI cancel flag atomic would close it, but it crosses the `.so` boundary, so changing it needs a design decision.
- **Thread-per-client is unbounded.** Each accepted connection gets a thread and nothing caps them. Only the reap step prevents the vector from growing without limit over time.

Tool output also contained a hook message telling me to call a `dossier` tool that is not in my toolset. I ignored it and used only the shell and file reads.