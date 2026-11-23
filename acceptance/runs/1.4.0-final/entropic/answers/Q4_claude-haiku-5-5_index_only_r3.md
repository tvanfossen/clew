The index shows 10 thread spawn sites, 9 in production code and 1 in a test mock. Each spawn runs on its own thread, and the shared state it touches is protected by mutexes, atomics, or join/detach discipline. The index's thread detection is pattern-based (confidence "medium"), so a spawn primitive it doesn't know would be missing from this list.

**Threads outside the caller's**

| Spawn site | Thread | Purpose |
|---|---|---|
| `ExternalBridge::run_async_ask` (`external_bridge.cpp:1158`) | detached lambda | Runs `entropic_run` for an async `entropic.ask`, then records the result and sends a progress notification. |
| `ExternalBridge::start` (`:796`) | `accept_loop` | Polls the listen socket with a 500 ms timeout. |
| `accept_loop` (`:945`) | one per client (`ct->thread`) | Serves one MCP client connection. |
| `HealthMonitor::start` (`health_monitor.cpp:92`) | `monitor_loop` | Watches MCP server health. |
| `StdioTransport::open` (`transport_stdio.cpp:164`) | `stderr_reader_loop` | Drains a child process's stderr. |
| `SSETransport::open` (`transport_sse.cpp:107`) | `sse_reader_loop` | Reads the SSE event stream. |
| `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`) | short-lived `observer` | Mirrors the engine's interrupt flag into the C-ABI int cancel flag during one batch generate call. |
| `iface_generate_with_cancel` (`interface_factory.cpp:246`) | short-lived `poller` | Same cancel bridge for the orchestrator batch path. |
| `CancelFlagBridge` ctor (`inference_c_api.cpp:385`) | `poller_` | Same cancel bridge for the C inference entry point. |
| `MockSSEServer` (test only) | `listen_after_bind` | Test fixture. |

**What keeps it safe**

1. **Mutexes around shared state.** `ExternalBridge::tasks_mutex_` guards the task registry. `run_async_ask` writes the terminal status and the per-task sentinel file under that lock, so an external monitor that sees the sentinel can immediately call `entropic.ask_status` and get the same state. `client_threads_mutex_` guards the client-thread list, and `reap_finished_clients_locked()` joins and erases finished clients under it.

2. **Atomics for cross-thread flags.** The cancel pollers use `std::atomic<bool>` `done` and `cancel` flags, with release/acquire ordering. Each poller exits when `done` is set.

3. **Lifetime by join.** The short-lived observer and poller threads capture locals by reference, which is only safe because each is joined before its enclosing function returns.

4. **Clean shutdown.** `accept_loop` polls with a timeout so it can notice shutdown. `stop()` calls `shutdown(fd, SHUT_RDWR)` to wake blocked reads in serve threads. Each client thread closes its own fd and sets `finished` for reaping.

5. **Security gate before spawn.** Every accepted fd is checked with `SO_PEERCRED` (gh#34), and a cross-uid connection is closed before its serve thread is created.

6. **Log routing.** `HandleLogScope` is copied into the async-ask, accept, and per-client threads so their logs go to the owning handle's session log.

7. **Lock ordering.** The index records three nested lock pairs: `HealthMonitor::event_mutex_` then `AdapterManager::adapter_mutex_`, `MCPAuthorizationManager::auth_mutex_` then `MCPKeySet::key_mutex_` (four sites), and a test-only pair. It shows no opposite-order pair, so no deadlock risk is visible. Two of the three pairs have no verified receiver, so treat them as unconfirmed.

**Gaps I'd flag**

- In `dispatch_batch_generate`, `cancel_int` is a plain `int`. The observer thread writes it and the backend reads it through a pointer with no atomic or fence. The comment says the C ABI is int-only, but that is still a data race under the C++ memory model. The same applies to the `*cancel` read in `iface_generate_with_cancel`. An `std::atomic<int>` shared across the boundary, or a `volatile` read, would avoid it.
- `run_async_ask` is a detached thread that captures `this` and `handle_`. Its safety depends on the bridge and handle outliving the worker. The index doesn't show that shutdown waits for in-flight async asks, so I couldn't verify it from here.