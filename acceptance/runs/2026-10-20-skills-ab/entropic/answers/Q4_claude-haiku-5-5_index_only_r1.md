**Threads outside the caller's**

The index's thread layer records five spawn sites in this repository, all `pthread`-kind, all `ast_spawn` with medium confidence:

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start`, `external_bridge.cpp:796` | Polls the listen socket every 500 ms, checks peer uid, and hands each connection to its own thread |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start`, `health_monitor.cpp:92` | Checks watched MCP servers and queues health events |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open`, `transport_stdio.cpp:164` | Forwards child-process stderr to the log |
| `SSETransport::sse_reader_loop` | `SSETransport::open`, `transport_sse.cpp:107` | Reads the SSE stream and parses events |
| `listen_after_bind` | `MockSSEServer`, in a test file | Test fixture only |

The index also records lambda-based threads that the thread layer does not list. These run outside the caller's thread:

- **Per-client serve threads.** `accept_loop` starts one `std::thread` per accepted client, which runs `serve_client(fd)`.
- **Async ask worker.** `run_async_ask` starts a detached `std::thread` that calls `entropic_run` and then broadcasts a `notifications/progress` message.
- **Cancel poller.** `CancelFlagBridge` (`inference_c_api.cpp:383`) polls an `int` cancel flag every 10 ms and sets an atomic.

**What keeps it safe**

- **Shared bridge state is mutex-guarded.** `tasks_mutex_` guards the task map in `run_async_ask`, including the sentinel write, which happens under the lock so a status poll sees the same terminal state. `client_threads_mutex_` guards the client-thread vector, and `reap_finished_clients_locked` runs under it.
- **Thread teardown is explicit.** A finished client thread sets an atomic `finished` flag. The accept loop joins and erases those entries, so the vector does not grow without bound. The loop itself uses `running_` (atomic) and a 500 ms poll, so shutdown is observed promptly.
- **Health monitor uses separate locks for separate jobs.** `watched_mutex_` guards the watch list during checks, `wake_mutex_` with a condition variable provides the sleep and early wake, and `event_mutex_` guards the event queue. `process_events` swaps the queue out under the lock and then invokes callbacks with the lock released. The index says callbacks run on the engine thread.
- **Hook dispatch does not hold locks while calling user code.** `HookRegistry` uses a `shared_mutex` per hook point. Registration takes the write lock, and dispatch takes the read lock only to copy a snapshot, then runs the callbacks outside it.
- **Cross-thread interrupts are designed for it.** `entropic_interrupt` is documented thread-safe and forwards to `AgentEngine::interrupt`. `ExternalMCPClient::interrupt` is documented safe to call from the engine's interrupt thread. `CancelFlagBridge` uses acquire/release atomics for its done and cancel flags.
- **Log routing follows the thread.** Spawned threads re-enter `HandleLogScope` with the owning handle's log id, so their log lines reach the right session log (gh#59).
- **Access control on the socket.** Each accepted fd is checked against `SO_PEERCRED` before a serve thread is spawned (gh#34).
- **Lock-order check.** The index reports three two-lock nestings and no pair taken in opposite orders, so it finds no deadlock risk. All three nestings rest on unverified receivers (`resolved_sites=0`), so treat them as unconfirmed. One of them, `event_mutex_` → `adapter_mutex_` via `swap` in `process_events`, looks like a receiver misattribution, since the `swap` there is on the local event vector.

**What the index cannot settle**

- **Lifetime of the detached async worker.** `run_async_ask`'s thread captures `this` and is detached. Nothing in the index shows that the bridge outlives it, and I did not find a join. The index does not show whether `stop()` waits for in-flight async tasks.
- **Thread-safety of the stdio and SSE `connected_` flags.** The index does not say whether they are atomic. The reader loops read them from their own threads.
- **Coverage.** The five-thread count covers only the spawn primitives this build recognises, and it omits the lambda spawns above. So "five threads" is not the full thread count of the engine.