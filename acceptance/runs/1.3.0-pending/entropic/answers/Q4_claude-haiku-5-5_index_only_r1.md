The index shows 10 thread spawn sites in entropic's own code, all `std::thread`/pthread, and no vendored ones. The main ones are below. Safety rests on a few repeated patterns, and I found two spots I could not confirm from the index.

**Threads that run off the caller's thread**

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::run_async_ask` worker | `external_bridge.cpp:1158` | Runs `entropic_run` for an async `entropic.ask`, then writes the final state and sends a progress notification |
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` | Polls the listen socket (500 ms timeout), checks peer uid, and spawns one serve thread per client (`:945`) |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Background health checking for MCP servers; queues events |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Drains a child process's stderr |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Reads the SSE stream |
| `ResponseGenerator::dispatch_batch_generate` observer | `response_generator.cpp:413` | Mirrors the engine's interrupt flag into the C-ABI cancel int for one batch call |
| `iface_generate_with_cancel` poller | `interface_factory.cpp:246` | Same idea for the orchestrator batch path |
| `CancelFlagBridge` poller | `inference_c_api.cpp:385` | Same idea for the C API cancellable generate |

The two `ExternalBridge` loops and the health monitor are long-lived. The observer and poller threads are short-lived, scoped to a single generation call.

**What keeps it safe**

1. **Queue handoff under a mutex.** `HealthMonitor::process_events` (`health_monitor.cpp:118`) takes `event_mutex_`, swaps `event_queue_` into a local vector, releases the lock, then invokes the callbacks on the engine thread. The monitor thread only ever touches the queue under the lock, and callbacks never run under it.

2. **Shared task state under one mutex.** `run_async_ask` updates `tasks_` only under `tasks_mutex_`. It writes the completion sentinel while still holding that lock, so any external reader who reacts to the sentinel sees the same terminal state the notification reports.

3. **Atomics for stop and cancel signals.** The accept loop checks `running_` (atomic). The poller threads use `std::atomic<bool>` for `done` and `cancel_flag`, with acquire/release ordering.

4. **Join before return.** The batch observer and the iface poller are joined before the function returns, so they cannot outlive the stack data they capture by reference.

5. **Per-client ownership.** Each `ClientThread` owns its fd and a `finished` atomic. `reap_finished_clients_locked()` joins and erases finished entries under `client_threads_mutex_`.

6. **Socket claim before bind.** `ExternalBridge::start` inserts the canonical socket path into the process-wide `s_bound_sockets` set under `s_bound_sockets_mu` before unlinking and binding. A second handle on the same path is refused rather than racing the unlink.

7. **Log scope propagation.** Each spawned thread installs a `HandleLogScope` with the owning handle's `log_id`, so logs from background threads go to the right session log.

**Lock ordering**

The index found 45 distinct mutex identities in this repo and three ordered nested pairs:
- `event_mutex_` → `adapter_mutex_` (in `process_events`, via `swap`)
- `auth_mutex_` → `key_mutex_` (in `check_access`)
- `mu_` → `adapter_mutex_` (in the test mock)

None of the pairs appears in the opposite order, so the index shows no deadlock risk. However, all three pairs have `resolved_sites: 0`, meaning the receiver of the call was never verified. Treat the ordering as unconfirmed.

**What I could not confirm**

- **Plain `int` cancel flags.** The batch observer writes `cancel_int` (a plain `int`, captured by reference) while the backend reads it through `int*`. The poller in `iface_generate_with_cancel` reads `*cancel` the same way. If the backend or caller does not use atomics on that int, that is a data race. The index does not show the backend's side, so I cannot settle it from here.
- **Detached async-ask thread.** The `run_async_ask` thread captures `this` and `handle_`. The visible body does not show a `detach()` call, and the rest of the function was truncated. I could not confirm how its lifetime is managed against `ExternalBridge` destruction, so that is the first thing to check in the source.