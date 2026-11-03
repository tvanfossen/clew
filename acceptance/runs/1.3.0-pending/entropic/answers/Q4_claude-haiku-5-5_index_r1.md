Entropic has **10 first-party thread spawn sites** (the index's count for the patterns it searches: `pthread` and `std::thread`). Two of them are test-only, so 8 run in production. They fall into two groups: long-lived background workers and short-lived per-call helpers. Safety comes from mutexes around shared state, atomics for cancel flags, and join-before-return for the helpers. I found two gaps that the index does not settle.

## Long-lived background threads

| Thread | Spawned at | What it does | Shared state and guard |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` (in `start`) | Polls the listen socket every 500 ms and gates each connection on `SO_PEERCRED` uid. | `client_threads_mutex_` guards the client-thread vector. |
| Per-client serve thread | `external_bridge.cpp:945` | Runs `serve_client` for one MCP connection. | Same `client_threads_mutex_`. `stop()` drains the vector, calls `shutdown(SHUT_RDWR)` to unblock reads, then joins. |
| Async-ask thread (`run_async_ask`) | `external_bridge.cpp:1158` | Detached thread that runs `entropic_run` for `entropic.ask`, then writes the sentinel and sends progress notifications. | `tasks_mutex_` guards `tasks_`. The sentinel is written while the lock is held, so an external reader sees the same terminal state the notification reports. |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Produces health events. | `event_mutex_` guards the queue. `process_events()` swaps the queue out under the lock, then runs callbacks after releasing it. Callbacks run on the engine thread. |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Drains a child process's stderr. | `io_mutex_` guards I/O. |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Reads the SSE stream. | `pending_mutex_` guards pending requests. |

## Short-lived helper threads

These run for one call and are joined before the call returns:

- `CancelFlagBridge` poller (`inference_c_api.cpp:385`), used by `entropic_inference_generate_with_cancel`.
- Poller in `iface_generate_with_cancel` (`interface_factory.cpp:246`).
- Observer in `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`), which mirrors the engine's `interrupt_flag_` into the C-ABI `int` cancel flag.

Their lambdas capture locals by reference (`&done`, `&observer_done`, `&cancel_int`). That is safe only because each one is joined on the normal return path before those locals go out of scope.

Test-only spawns (`listen_after_bind` in `transport_sse_test.cpp`, and the mock SSE server) are excluded above.

## What keeps it safe

1. **Shared maps and queues sit behind a named mutex.** Each background thread takes one of the locks listed above for each access. The index records 45 lock identities in the first-party code.
2. **Lock-free flags use atomics.** `running_`, `done_`, `cancel_`, `observer_done` and `interrupt_flag_` are atomics.
3. **Shutdown is ordered.** `ExternalBridge::stop()` sets `running_` false, closes the listen fd, joins the accept thread, then shuts down and joins each client thread. `HealthMonitor` drains its queue outside the lock. The short-lived helpers join unconditionally on return.
4. **Log context follows the thread.** Each thread opens a `HandleLogScope` so its logs go to the owning handle's session log (gh#59).
5. **Lock nesting is shallow.** The index records three two-lock pairs and no reversed pair, so no deadlock cycle shows up. However, two of those pairs have `resolved_sites=0`, which means the receiver was never verified, so I would not call the ordering confirmed.

## Gaps I found

- **Unsynchronised `int` cancel flag.** The helpers read `*cancel` and write `cancel_int` as plain `int`, with no atomic. The observer in `dispatch_batch_generate` writes it on one thread while the backend poller reads it on another. That is a data race under the C++ memory model, even if it is benign in practice on x86. The comment says the C ABI is `int*`-only, but an `std::atomic_ref` or a `.so`-safe atomic would fix it without changing the ABI shape.
- **Detached async-ask thread is not joined by `stop()`.** `run_async_ask` captures `this` and `handle_` in a detached `std::thread`. It is not in `client_threads_`, so `stop()` does not wait for it. I did not verify whether `entropic_destroy` waits for in-flight tasks some other way. If it does not, destroying the handle while an ask is running is a use-after-free.
- **Helpers have no exception guard.** If `orchestrator->generate` throws in `iface_generate_with_cancel`, the joinable `poller` destructor calls `std::terminate`. There is no RAII join guard.
- **The `HealthMonitor` nesting row looks wrong.** The index attributes `event_mutex_ → adapter_mutex_` to `process_events`. The body I read holds only `event_mutex_`, and it invokes callbacks after releasing it, so that pair likely comes from a bad receiver match, not a real nesting.