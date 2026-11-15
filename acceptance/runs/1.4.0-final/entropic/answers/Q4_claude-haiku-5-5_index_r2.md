Ten spawn sites in first-party code, per the index's pattern set. Most are scoped helpers that are joined before their caller returns. Two long-lived groups need the most attention: the external bridge and the MCP transports.

| Spawn site | Thread | Lifetime | Teardown |
|---|---|---|---|
| `ExternalBridge::start` (`external_bridge.cpp:796`) | `accept_loop` | Bridge lifetime | Joined in `stop()` |
| `ExternalBridge::accept_loop` (`:945`) | one `serve_client` per connection | Connection lifetime | `shutdown(SHUT_RDWR)` then join in `stop()` |
| `ExternalBridge::run_async_ask` (`:1158`) | async `entropic.ask` worker | Task lifetime | **Detached** (`:1222`), never joined |
| `HealthMonitor::start` (`health_monitor.cpp:92`) | `monitor_loop` | Monitor lifetime | Joined in `stop()` (`:108`) |
| `StdioTransport::open` (`transport_stdio.cpp:164`) | `stderr_reader_loop` | Transport lifetime | Joined (`:219`) |
| `SSETransport::open` (`transport_sse.cpp:107`) | `sse_reader_loop` | Transport lifetime | Joined (`:139`) |
| `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`) | `observer` | One batch call | Joined before return (`:429`) |
| `iface_generate_with_cancel` (`interface_factory.cpp:246`) | `poller` | One batch call | Joined before return (`:262`) |
| `CancelFlagBridge` (`inference_c_api.cpp:385`) | `poller_` | RAII object | Joined in destructor (`:403`) |
| Test-only: `MockSSEServer` | `listen_after_bind` | Test | Not production |

**What keeps it safe**

- **Cross-thread state is mutex-guarded.** The bridge's task registry is under `tasks_mutex_`, and `client_threads_mutex_` guards the client list. The process-wide socket-path claim is under `s_bound_sockets_mu`, so two handles in one process cannot bind the same socket. Health monitor, stdio and SSE transports each have their own mutex.
- **Flags are atomics.** `running_`, the poller `done` and `cancel` flags, the `finished` flag on each client thread, and the engine's `interrupt_flag_` are all atomics. The C ABI carries only `int*`, so no `std::atomic` crosses the `.so` boundary.
- **Ordering is deliberate.** The terminal sentinel file is written under `tasks_mutex_` before the completion notification fires, so an external monitor reacting to the sentinel sees the same state that `ask_status` returns.
- **Scoped helpers cannot outlive their caller.** The batch observer and cancel poller capture stack locals by reference, which is only safe because they are joined before return.
- **`stop()` drains in order.** It closes the listen socket, joins the accept thread so no new clients spawn, shuts down each client fd to wake blocked reads, then joins each client thread.
- **Access control precedes spawn.** Each accepted fd is checked with `SO_PEERCRED` before a serve thread is created.
- **Log routing survives the thread hop.** Each thread body installs a `HandleLogScope`, so its logs reach the owning handle's session log.

**Lock ordering.** The index reports three two-lock nestings and no opposite-order pair among them: `event_mutex_` then `adapter_mutex_` in the health monitor, `auth_mutex_` then `key_mutex_`, and the mock server's `mu_` then `adapter_mutex_`. The index marks all three as having zero resolved call sites, so I would not call the ordering verified. I did not sweep all 45 lock identities.

**The gap: detached async-ask thread.** `run_async_ask` captures `this` and `handle_`, runs `entropic_run(handle_, …)`, and then detaches. Nothing I read joins or counts it:

- `ExternalBridge::stop()` does not wait for in-flight async tasks.
- `entropic_destroy` (`src/facade/entropic.cpp:1877`) calls `external_bridge->stop()`, then destroys the orchestrator interface, then `delete handle`.
- The only drain path I found is `cancel_inflight_async_tasks`, which runs on `entropic.context_clear`, not on destroy.

So if a handle is destroyed while an async ask is running, the detached thread can dereference a deleted bridge and handle. I have not reproduced this, and it is possible the caller is documented to drain first. That contract is not visible in what I read. The fix is to keep an in-flight count on the bridge and have `stop()` wait for it, or to replace the detach with a tracked thread that is joined.