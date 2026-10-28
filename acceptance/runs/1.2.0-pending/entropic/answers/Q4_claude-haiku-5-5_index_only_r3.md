Ten thread spawn sites in first-party code were matched by the index. Every one is a spawn the index found; I did not check for spawn primitives it doesn't know about.

| Thread | Spawned from | What it does off-caller |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` | Polls the listen socket and accepts clients |
| per-client `serve_client` thread | `accept_loop` (`ct->thread`) | Serves one MCP client until disconnect |
| `run_async_ask` worker (lambda) | `ExternalBridge::run_async_ask`, detached | Runs `entropic_run` for an async ask |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` | Periodic health checks on MCP servers (body not read) |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` | Drains child-process stderr |
| `SSETransport::sse_reader_loop` | `SSETransport::open` | Reads the SSE event stream |
| `ResponseGenerator` observer | `dispatch_batch_generate` | Mirrors the engine interrupt flag into the C-ABI int |
| `iface_generate_with_cancel` poller | `interface_factory.cpp` | Bridges the cancel int to the orchestrator's atomic |
| `CancelFlagBridge` poller | `inference_c_api.cpp` | Same bridge for the C API cancel path |
| `ExternalBridge` test/mock threads | tests only | Not runtime |

Two of the ten are test-only (`MockSSEServer`'s `listen_after_bind` and the `transport_sse_test` mock), so the runtime count is eight. The index doesn't split the rest by target, so I count them all as first-party.

**What keeps them safe**

- **Shared state is behind named mutexes.** The index lists 45 distinct lock identities in this repo, including `tasks_mutex_`, `client_threads_mutex_`, and `s_bound_sockets_mu` in `ExternalBridge`, `event_mutex_`/`watched_mutex_` in `HealthMonitor`, and `io_mutex_`/`pending_mutex_` in the transports.
- **Lock ordering is recorded.** Three nested pairs were observed: `auth_mutex_` → `key_mutex_`, `event_mutex_` → `adapter_mutex_`, and `mu_` → `adapter_mutex_` in the test mock. None appear in opposite order. However, all three have zero resolved call sites, so this is weak evidence and I wouldn't claim it's deadlock-free.
- **Task state and the sentinel are written together.** In `run_async_ask`, the terminal status, the result, and `write_sentinel` all happen under `tasks_mutex_`. An external monitor that sees the sentinel can call `ask_status` and get the same state.
- **Socket ownership is claimed before unlinking.** `start()` inserts the canonical path into the process-wide `s_bound_sockets` set under `s_bound_sockets_mu` before `create_listen_socket` unlinks anything. This blocks two in-process bridges from stealing each other's socket. `stop()` releases the claim.
- **Clients are gated and drained.** `accept_loop` closes any fd whose peer uid doesn't match (SO_PEERCRED). `stop()` sets `running_` false, closes the listen fd, joins the accept thread, calls `shutdown(SHUT_RDWR)` on each client fd to unblock reads, then joins the client threads.
- **Per-handle logs stay attributed.** Every spawned body installs a `HandleLogScope` with the owning handle's log id, so logs from background threads go to the right session.
- **Cancel pollers are joined before the caller returns.** The poller and observer threads in `iface_generate_with_cancel` and `dispatch_batch_generate` use an `atomic<bool>` done flag, and the caller joins them before returning, so their stack captures stay valid.
- **The async ask is fire-and-forget.** `run_async_ask` ends with `.detach()`, so nothing joins it. Its shared state is the `tasks_` map under `tasks_mutex_`, and its completion notification is a short `notifications/progress` message rather than the result body.

**Caveat:** the cancel path shares a plain `int` through a pointer. The observer thread writes `cancel_int = 1` and the backend poller reads `*cancel` with no atomic or lock. The join makes the lifetime safe, but the concurrent read and write are a C++ data race. The `atomic<bool>` inside the poller is the only synchronized part. I'd make the shared int a `std::atomic<int>` or give the C ABI an atomic, which the code comments say was avoided to keep the boundary `int*`-only.

I did not read the body of `HealthMonitor::monitor_loop`, so its locking is inferred only from the lock index.