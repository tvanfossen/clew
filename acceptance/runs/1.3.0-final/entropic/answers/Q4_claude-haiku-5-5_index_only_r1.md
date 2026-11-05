The index shows 10 first-party thread spawn sites and 45 lock identities. It does not show the bodies of the stdio and SSE reader loops or the producer side of the health-event queue, so those parts are only partly covered below.

**Threads that run off the caller's thread**

| Spawn site | Thread | What keeps it safe (per the index) |
|---|---|---|
| `ExternalBridge::start` (`external_bridge.cpp:796`) | `accept_loop` | Polls the listen fd with a 500 ms timeout and checks `running_`, an atomic, so shutdown is observed. Every accepted fd is checked with `peer_uid_matches` (SO_PEERCRED) before a thread is made for it. Each client gets its own `ClientThread`, held in `client_threads_` under `client_threads_mutex_`. Finished clients are reaped under that lock. `stop()` calls `shutdown(fd, SHUT_RDWR)` to wake blocked reads. |
| `ExternalBridge::accept_loop` (`:945`) | per-client `serve_client` | Owns its fd and closes it on exit. Sets an atomic `finished` flag for the reaper. `serve_client` unsubscribes via an RAII guard. The handle log scope is propagated, so logs route to the owning session. |
| `ExternalBridge::run_async_ask` (`:1158`) | detached async-ask worker | Task state is in `tasks_` under `tasks_mutex_`. The terminal status and the sentinel file are written under that lock, before the progress notification goes out. Log scope is propagated. |
| `HealthMonitor::start` (`health_monitor.cpp:92`) | `monitor_loop` | `watched_` is held under `watched_mutex_` while checks run. The wait is on `wake_cv_` with a `!running_` predicate. The loop does not hold `event_mutex_` while it runs. |
| `StdioTransport::open` (`:164`) | `stderr_reader_loop` | Body not in the index. The class owns `io_mutex_`. |
| `SSETransport::open` (`:107`) | `sse_reader_loop` | Body not in the index. The class owns `pending_mutex_`. |
| `CancelFlagBridge` ctor (`inference_c_api.cpp:385`) | poller | Starts only when the cancel pointer is non-null. Stops on an atomic `done_`. The `CancelFlagBridge` class joins it in its destructor. |
| `iface_generate_with_cancel` (`interface_factory.cpp:246`) | poller | `done` and `cancel_flag` are atomics. The thread is joined before the function returns. |
| `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`) | `observer` | Mirrors the engine's atomic `interrupt_flag_` into the int cancel flag. Stops on `observer_done`. It is joined before return. |
| Test-only spawns | `listen_after_bind`, `MockSSEServer` | Test code, not production. |

The main pattern is that each background thread either owns its resources (fds, the `ClientThread` record) or is stopped and joined by its owner. Shared state sits behind a named mutex, and the health monitor runs its user callbacks on the engine thread via `process_events`, not on the monitor thread.

**Concerns the index raises**

- **Data race on the cancel int.** The C-ABI `int* cancel` is read by the poller threads with plain loads (`*cancel != 0`), and the observer thread writes `cancel_int = 1` with a plain store. Only the atomics around them are synchronized. The `int` is what crosses the `.so` boundary by design, but in C++ terms this is an unsynchronized write and read. The fix would be an atomic or a volatile-free wrapper on the engine side.
- **Detached async worker.** `run_async_ask` uses a detached `std::thread` that captures `this`. The index shows no join or ownership record for it. Whether the bridge outlives it in shutdown is not shown. I'd check this one first.
- **File I/O under `tasks_mutex_`.** `write_sentinel` runs while `tasks_mutex_` is held, so a slow filesystem stalls every task query.
- **Lock nestings.** The index lists three two-lock pairs. None has a confirmed resolved call site (`resolved_sites=0` on all three). One, `event_mutex_` → `adapter_mutex_` in `process_events`, looks like a name collision: `events.swap(event_queue_)` seems to have resolved to an `AdapterManager` swap. I would not cite it as a real nesting or as a deadlock risk. The index found no opposite-order pair, so no deadlock is reported.

If you want the stdio and SSE reader bodies, or the event producer, those need a source read. The index doesn't have them.