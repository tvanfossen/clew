Five background threads are spawned by the index's pattern match, plus several more it does not see. Safety rests on atomics, per-object mutexes, joins on shutdown, and per-thread log scoping. Two spots look weak.

**Thread inventory**

| Thread | Spawned in | Lifecycle | Shared state and guard |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` | Joined in `stop()` | `running_` (atomic). `poll` with a 500 ms timeout so it notices shutdown. |
| Per-client `serve_client` | `external_bridge.cpp:945` | Spawned per accepted fd, joined by `reap_finished_clients_locked()` or `stop()` | `client_threads_` under `client_threads_mutex_`. Each thread sets an atomic `finished` flag before exit. |
| Async ask worker (`run_async_ask`) | `external_bridge.cpp:1158`, then `.detach()` at `:1222` | Detached, never joined | `tasks_` and sentinel writes under `tasks_mutex_`. Phase observer uses `observer_gen_` (atomic) plus `active_task_id_` under the mutex. |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Joined in `stop()` after `notify_all` | `watched_` under `watched_mutex_`. Waits on `wake_cv_` with `wake_mutex_`. `running_` is atomic. |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Reads only, exits when `connected_` clears | `connected_` (atomic). `poll` with a 500 ms timeout. |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Blocking `httplib` GET, exits on disconnect | `connected_` and `running_` (atomic). Pending requests under `pending_mutex_`. |
| `CancelFlagBridge` poller | `inference_c_api.cpp:385` | RAII. Destructor sets `done_` and joins | Bridges `int*` to `std::atomic<bool>` on a 10 ms poll. |
| Response observer | `response_generator.cpp:413` | Joined before return | `observer_done` atomic. Lambda captures locals by reference, safe because of the join. |
| Iface cancel poller | `interface_factory.cpp:246` | Joined before return | `done` atomic. Writes `cancel_flag` atomic. |

The index reports only the first five. The last four were found by grepping `std::thread`, so the index's pattern set misses them. The detached async worker is the one that matters most. Its `.detach()` means `stop()` cannot wait for it, and it captures `this` and `handle_`. I did not verify whether the destructor waits on in-flight async tasks. A backlog proposal (`P2-20260429-001`) already calls the unbounded detach a known problem.

**What keeps it safe**

- **Atomics for flags, mutexes for state.** Every cross-thread flag (`running_`, `connected_`, `done`, `observer_done`, `observer_gen_`) is atomic. Collections and task maps sit behind a named mutex. Those mutexes are not held across blocking I/O.
- **Shutdown ordering in `ExternalBridge::stop()`** (`external_bridge.cpp:826`). It clears `running_`, closes the listen fd, and joins the accept thread. It then moves the client list out under the mutex, calls `shutdown(SHUT_RDWR)` on each client fd to wake blocked reads, and joins each client thread.
- **Bounded waits.** Accept, stderr, and the cancel pollers use 500 ms or 10 ms timeouts, so they notice shutdown without needing a signal.
- **Join-on-destroy RAII** for the cancel pollers and the observer, so no thread outlives its stack-captured references.
- **Log context propagation.** Each spawned lambda opens a `HandleLogScope(log_id)`, so logs from worker threads go to the owning handle's session log.
- **Security gate.** `peer_uid_matches()` (`SO_PEERCRED`) closes cross-uid connections before a serve thread is created.
- **Engine-thread callbacks.** `HealthMonitor::process_events()` drains a queue and runs callbacks on the engine thread, so the monitor thread never calls user code directly.
- **C ABI boundary.** The threads are internal to the `.so`, and no C++ objects cross the boundary.

**Weak spots I found**

1. **Plain `int` cancel flags.** `response_generator.cpp:413` and `interface_factory.cpp:246` write and read a plain `int`, or `int*`, from two threads. The `int*` is what the C ABI exposes, so this is a formal data race, not one protected by an atomic. The design comment says the boundary is `int*`-only on purpose. The race is benign in practice on the loop's 10 ms polling, but it is unsynchronized.
2. **`listen_fd_` is a plain `int`** (`external_bridge.h:385`). `stop()` writes it to `-1` while `accept_loop` reads it on each iteration. The ordering comes only from `running_` being checked first. The worst outcome is an `EBADF` from `accept()` followed by a clean exit, but there is no formal synchronization.
3. **Detached async worker.** As noted above, nothing joins it, so its captured `this` and `handle_` must outlive it. I did not confirm that the destructor drains in-flight tasks.
4. **`HealthMonitor::start()` check-then-set** (`health_monitor.cpp:88-91`). It reads `running_`, then assigns it, which is not atomic as a pair. This is fine only if `start()` is always called from one thread.

I did not check the `StdioTransport` and `SSETransport` close paths for join ordering. Their threads are read-only or exit on disconnect, so I expect them to be safe, but I did not confirm it.