Entropic has 10 thread spawn sites in its own source, found by the index's spawn-pattern search. Most of them are small poller or reader loops. Safety comes mostly from one pattern: a single mutex guards each shared structure, and the thread's results are handed back through that mutex or an atomic. A few spots rely on plain `int` flags or on lifetimes I could not fully verify.

**Threads that run off the caller's thread**

| Thread | Spawned in | What it does | How it stays safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` | Polls the listen socket, rejects other UIDs, starts one thread per client | `client_threads_mutex_` guards the vector. `stop()` closes the listen fd, joins the accept thread, then `shutdown(SHUT_RDWR)`s and joins each client |
| Per-client `serve_client` | `accept_loop` | Serves one MCP client | Each gets its own `ClientThread` with an atomic `finished` flag. The vector is reaped under the same mutex |
| `ExternalBridge::run_async_ask` worker | `run_async_ask` (`external_bridge.cpp:1142–1222`) | Runs `entropic_run` for `entropic.ask` in the background | `tasks_mutex_` guards the task registry. The sentinel is written under that same lock, before the progress notification fires |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` | Periodic MCP server health checks | `event_mutex_` guards the queue. `process_events()` swaps the queue out under the lock, then runs callbacks on the engine thread |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` | Drains child stderr | `io_mutex_` on the transport |
| `SSETransport::sse_reader_loop` | `SSETransport::open` | Reads the SSE stream | `pending_mutex_` guards pending requests |
| `ResponseGenerator::dispatch_batch_generate` observer | `dispatch_batch_generate` (`response_generator.cpp:413`) | Mirrors the engine's `interrupt_flag_` into the C-ABI `int` cancel flag | Joined before the function returns, so it captures locals by reference safely |
| `iface_generate_with_cancel` poller | `interface_factory.cpp:246` | Same cancel bridge for the orchestrator path | Joined before return |
| `CancelFlagBridge` poller | `inference_c_api.cpp:385` | Cancel bridge for `entropic_inference_generate_with_cancel` | `done_` and `cancel_` are atomics. Destructor joins |

There are also two test-only spawns (`MockSSEServer`'s `listen_after_bind` and a test observer). I left them out.

**What keeps it safe**

- **One lock per structure, and RAII everywhere.** Lock identities are high-confidence in the index. Examples are `tasks_mutex_`, `event_mutex_`, `client_threads_mutex_`, `io_mutex_` and `pending_mutex_`.
- **Swap-out-then-dispatch.** `HealthMonitor::process_events` swaps the queue under `event_mutex_` and runs the callbacks outside the lock, so callbacks never run while the lock is held.
- **Ordering the sentinel under the lock.** `run_async_ask` writes the sentinel under `tasks_mutex_`, so an external poller that sees the file also sees the terminal state in the registry.
- **Explicit teardown.** `ExternalBridge::stop()` shuts down client sockets to unblock their `read()` calls, then joins them. Poller threads are joined before their owning call returns.
- **Atomics for flags read across threads.** The `CancelFlagBridge` and the `done` flags use `std::atomic`, which matches the architecture rule "atomic for state queries, mutex for transitions."

**Lock nesting**

The index found three two-lock pairs. The one I'd question is `event_mutex_ → adapter_mutex_` in `HealthMonitor`. The `process_events` body only takes `event_mutex_`, so the index may have attributed the `swap` call wrongly. All three pairs show zero resolved call sites, so none of them is confirmed. The index reports no opposite-order pair, so it flags no deadlock.

**Risks I'd check before relying on this**

1. **Detached async-ask worker outlives `stop()`.** `run_async_ask` ends with `.detach()` (`external_bridge.cpp:1222`). The lambda captures `this` and `handle_`. `stop()` joins the accept and client threads but never waits on the detached worker. If the bridge or handle is destroyed while an `entropic.ask` is still running, the worker touches freed memory. I did not verify whether the destructor or `cleanup_expired_tasks` waits for running tasks. That needs a look.
2. **Plain `int` cancel flags across threads.** The observer and poller threads write a plain `int` (`cancel_int`, `*cancel`), and the backend reads it through a pointer with no atomic. That is a data race under the C++ memory model. It probably works on the target hardware, but a compiler may hoist the read out of the backend's loop. The header comment says the `int*` choice avoids atomics across the `.so` boundary, so the fix may need a C-ABI atomic type or a volatile read. I'd treat this as a real finding, not a style issue.
3. **Thread count is pattern-bound.** The index counts only spawn primitives its patterns match. A thread spawned by a wrapper or a platform API outside those patterns is not in the 10.

Source for the findings: `src/facade/external_bridge.cpp`, `src/core/response_generator.cpp`, `src/inference/interface_factory.cpp`, `src/inference/inference_c_api.cpp`, `src/mcp/health_monitor.cpp`.