The threads that outlive a single call are all in the MCP bridge, the health monitor, the transports, and short-lived cancel pollers. Safety comes from mutexes around shared registries, atomics for flags, join-on-stop, and one unbounded case I'd flag.

**Long-lived threads**

| Thread | Where | Lifetime and shutdown |
|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Started in `start()`. `stop()` closes the listen fd and joins it (`:826-834`). |
| Per-client serve threads | `external_bridge.cpp:945`, tracked in `client_threads_` | `stop()` drains the vector, calls `shutdown(SHUT_RDWR)` to wake blocked reads, then joins each one (`:840-851`). Finished ones are reaped during accept (`:956`). |
| Health monitor | `src/mcp/health_monitor.cpp:92` | `stop()` sets `running_` false, notifies the CV, and joins (`:102-111`). Events are queued under `event_mutex_` and callbacks run on the engine thread in `process_events()` (`:118-129`). |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Started in `open()`. I read the start path and the `running_` flag, but not the join in `close()`. |
| Stdio stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Not checked. |

**Short-lived pollers (batch cancel bridges)**

These exist because the C ABI takes an `int*` cancel flag and the backend wants an atomic. Each one polls every 10 ms and is joined before the function returns:
- `CancelFlagBridge` (`src/inference/inference_c_api.cpp:376-420`), joined in its destructor.
- The streaming observer in `src/core/response_generator.cpp:409-429`. It captures stack references, which is safe only because it is joined on the same path.
- `iface_generate_with_cancel` in `src/inference/interface_factory.cpp:242-262`.

**The unbounded one: async ask workers**

`ExternalBridge::run_async_ask` spawns `std::thread(...).detach()` per `entropic.ask` (`external_bridge.cpp:1158-1222`). The thread captures `this` and `handle_`, and nothing joins it. `stop()` and the destructor (`:612-614`) do not wait for it. `handle_clear` cancels in-flight tasks but polls for only about 1 s (`:434-443`), and its own comment says detached workers "may still be in flight when this returns." If the bridge or engine is destroyed while a worker is still running, the worker dereferences freed state. The backlog proposal `.claude/proposals/BACKLOG/P2-20260429-001-async-bridge-io-architecture.md` describes this same problem, with no bound on concurrent workers. I did not find a test that exercises it.

**What keeps the rest safe**

- Shared registries are mutex-guarded: `tasks_mutex_` for `tasks_`, `subscribers_mutex_`, `client_threads_mutex_`, and `s_bound_sockets_mu` for the process-wide socket registry.
- The completion sentinel is written under `tasks_mutex_` before the progress notification goes out, so a poller that reacts to the notification sees the same state (`:1171-1183`).
- Stale phase-observer callbacks are discarded with a generation counter (`attached_gen_`, `:1092`, `:1120`).
- Thread-local log routing uses a `HandleLogScope` installed at the top of each thread body, so logs from these threads go to the right handle's session log.
- Flags are `std::atomic` (`running_`, the cancel atomics), and the socket-level wakeups are explicit `shutdown()` calls, not just flag checks.

**Gaps I'd raise**

1. Detached async-ask workers have no join or lifetime guard. This is the real hazard. A fix would track workers and join them in `stop()`, or hold them in a bounded pool, as the P2 proposal suggests.
2. The pollers share a plain `int` across threads with no atomic. The `int*` is forced by the C ABI, so the poller's writes and the backend's reads are a data race under the C++ memory model. I did not trace how the backend reads the flag, so I can't say whether it is a practical problem.