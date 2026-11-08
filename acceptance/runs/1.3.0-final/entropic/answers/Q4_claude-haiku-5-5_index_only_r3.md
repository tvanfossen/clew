Ten spawn sites in this repo run on threads other than the caller's, per the index. They fall into three groups, and each group has a different safety mechanism.

**1. Background services started at init**
- `HealthMonitor::monitor_loop` (`src/mcp/health_monitor.cpp:92`, started by `HealthMonitor::start`) polls every 500ms. It holds `watched_mutex_` while it checks servers, then waits on `wake_cv_` under `wake_mutex_`. Shutdown is a flag (`running_`) checked by the predicate of that wait.
- `ExternalBridge::accept_loop` (`src/facade/external_bridge.cpp:796`, started by `ExternalBridge::start`) uses `poll()` with a 500ms timeout so it can see shutdown. Each accepted client gets its own thread, which is stored in `client_threads_` under `client_threads_mutex_`. Finished threads are reaped. Every fd is checked with `SO_PEERCRED` (uid match) before a thread is created.
- `ExternalBridge` per-client `serve_client` threads (`accept_loop` line 945) own their fd and close it on exit. A RAII guard unsubscribes the client on any exit path.

**2. Per-request workers**
- `ExternalBridge::run_async_ask` (`external_bridge.cpp:1158`) runs `entropic_run` in a detached thread. It inserts the task under `tasks_mutex_`, then re-takes that lock to store the final result and write the sentinel file before the completion notification goes out. This ordering is deliberate: a monitor that reacts to the sentinel sees the same terminal state that `entropic.ask_status` returns. The thread also gets a `HandleLogScope` so its logs go to the owning handle's session log.
- `ResponseGenerator::dispatch_batch_generate` (`src/core/response_generator.cpp:413`) starts an observer thread that mirrors the engine's `interrupt_flag_` (atomic) into an `int` cancel flag for the duration of one call. It sets `observer_done` with release/acquire ordering and joins before returning, so the thread never outlives the call. The `int` keeps atomics out of the C ABI.
- Two cancel pollers: `iface_generate_with_cancel` (`src/inference/interface_factory.cpp:246`) and `CancelFlagBridge` (`src/inference/inference_c_api.cpp:385`). Both use the same pattern: a 10ms poll of an `int` flag, a `done` flag, and a join before return.

**3. Transport readers**
- `SSETransport::sse_reader_loop` (`src/mcp/transport_sse.cpp:107`) and `StdioTransport::stderr_reader_loop` (`src/mcp/transport_stdio.cpp:164`) read from the socket or child stderr. The stderr reader polls with a 500ms timeout and exits when `connected_` clears. The SSE reader's shared state is `pending_mutex_` (in `SSETransport`), and I did not dossier its critical sections.

**What keeps it safe**
- Shared maps and queues are guarded by named mutexes, and every critical section I checked is a RAII `lock_guard` or `unique_lock`. Examples are `tasks_mutex_`, `client_threads_mutex_`, `watched_mutex_`, and `event_mutex_`.
- `HealthMonitor::process_events` swaps the event queue out under `event_mutex_` and runs callbacks after releasing it. Callbacks therefore run on the engine thread without holding the lock.
- Stop and join are explicit. Atomic flags (`running_`, `done`, `observer_done`) signal shutdown, and every worker that is joined is joined before the function that owns it returns.
- Lock-order evidence is thin. The index records three two-lock pairs across six sites, and it has no opposite-order pair, so it flags no deadlock. However, every pair has `resolved_sites=0`, meaning the receiver was never verified. Treat the ordering as unconfirmed, not as checked. The pairs are `event_mutex_`→`adapter_mutex_` (via `process_events`, which I believe is a misparse of `swap` on the queue), `auth_mutex_`→`key_mutex_` (in `check_access`, 4 sites), and `mu_`→`adapter_mutex_` (in a test mock).

**Limits**
- The 10 spawn sites come from the `std::thread`/pthread patterns this build searches. A platform primitive or a project spawn helper outside those patterns would not appear. Declaring a `thread_patterns` section would widen the search.
- I did not verify the reader threads' lock sections or the cross-thread `interrupt_flag_` ownership.