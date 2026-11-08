**Short answer:** Ten spawn sites in this repository run work off the caller's thread. Shared state is guarded by a small set of named mutexes, cancellation uses atomics polled every 10 ms, and worker threads are joined in a fixed order at shutdown. Some pieces of the safety argument are not verified, which I flag at the end.

**Threads that run off the caller's thread** (the index's pattern-based spawn scan found 10 sites, all in this repo, medium confidence):

| Thread | Spawned from | Lifetime |
|---|---|---|
| `ExternalBridge::accept_loop` | `start()`, `external_bridge.cpp:796` | Long-lived; polls the listen socket every 500 ms |
| Per-client `serve_client` threads | `accept_loop`, `external_bridge.cpp:945` | One per connected MCP client |
| Async `entropic.ask` worker (lambda in `run_async_ask`) | `external_bridge.cpp:1158` | Detached; runs `entropic_run` for one task |
| `HealthMonitor::monitor_loop` | `start()`, `health_monitor.cpp:92` | Long-lived |
| `StdioTransport::stderr_reader_loop` | `open()`, `transport_stdio.cpp:164` | Per stdio MCP server |
| `SSETransport::sse_reader_loop` | `open()`, `transport_sse.cpp:107` | Per SSE MCP server |
| Batch cancel observer | `ResponseGenerator::dispatch_batch_generate`, `response_generator.cpp:413` | Short-lived, per batch call |
| Batch cancel poller | `iface_generate_with_cancel`, `interface_factory.cpp:246` | Short-lived, per call |
| `CancelFlagBridge` poller | `inference_c_api.cpp:385` | Scoped to one cancellable generate |

Two more spawn sites are test-only (`MockSSEServer`).

**What keeps it safe**

1. **Named mutexes around shared state.** `ExternalBridge` uses `tasks_mutex_` for the task registry and `client_threads_mutex_` for the client-thread vector. `HealthMonitor` uses `event_mutex_`, `watched_mutex_` and `wake_mutex_`. Across the repo the index lists 45 distinct lock identities.
2. **Drain-then-dispatch.** `HealthMonitor::process_events` swaps the event queue out under `event_mutex_`, then invokes callbacks with the lock released. The callbacks run on the engine thread, not the monitor thread (`health_monitor.cpp:118`).
3. **Ordering inside the critical section.** In `run_async_ask`, the sentinel file is written under `tasks_mutex_`, together with the status update and before the progress notification. An external watcher that reacts to the sentinel therefore sees the same terminal state as `ask_status`.
4. **Atomics for cancellation.** The cancel and interrupt flags are `std::atomic`, polled every 10 ms by the observer and poller threads. The C ABI carries only `int*`, so no atomic crosses the `.so` boundary (`response_generator.cpp:379`).
5. **Join-before-return.** Pollers and observers take a `done` flag and are joined before the function returns. `ExternalBridge::stop()` runs in a fixed order: clear `running_`, close the listen fd, join the accept thread, `shutdown(SHUT_RDWR)` each client fd to wake its blocked read, join client threads, then remove the socket file and release the bound-path claim.
6. **Access control on accept.** `SO_PEERCRED` is checked before a serve thread is spawned, and a mismatched uid is closed immediately (`accept_loop`, gh#34).
7. **Log context propagation.** Worker threads install a `HandleLogScope` so their logs land in the owning handle's session log.

**Gaps and caveats**

- **Detached async worker.** The `run_async_ask` thread captures `this` and is detached. Nothing I read ensures the `ExternalBridge` outlives it, so a destroy during a running task looks like a use-after-free risk. I could not confirm a guard from the index. This is the most important item to check.
- **Lock-nesting records are unverified.** The index lists three nested-lock pairs, but every one has `resolved_sites=0`. The `event_mutex_` → `adapter_mutex_` pair at `health_monitor.cpp:122` looks like a misattributed `swap` call, because the `process_events` body I read takes no `adapter_mutex_`. No opposite-order pair appears, so the index raises no deadlock flag, but I would not cite these pairs as confirmed.
- **Thread-safety classes.** `entropic.h` says each function documents its thread-safety class. I did not read those per-function classes.
- **Spawn coverage.** Detection is pattern-based. Spawns through a project helper or a platform API outside the searched primitives would not appear in the count of 10.