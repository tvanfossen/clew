The index shows 9 spawn sites in production code, plus one in a test mock. Each thread is safe for a different reason, and the mechanisms are mostly mutexes, atomics, and "do the work on the owning thread."

**Threads that run off the caller's thread** (from `search` on threads, spawn sites all `ast_spawn`, confidence medium)

| Thread | Spawned at | What it does | What keeps it safe |
|---|---|---|---|
| Async `entropic.ask` worker (`run_async_ask` lambda) | `external_bridge.cpp:1158` | Runs `entropic_run` detached, then records the result | `tasks_mutex_` guards the task map. Terminal state and the sentinel file are written under the same lock, so an external monitor that sees the sentinel can read the same status via `ask_status`. |
| Accept loop | `external_bridge.cpp:796` | Polls the listen fd, accepts clients | `poll` with a 500 ms timeout so it can see shutdown. Each connection's uid is checked with `SO_PEERCRED` before a thread is spawned. |
| Per-client serve thread | `external_bridge.cpp:945` | Serves one MCP client | Pushed into `client_threads_` under `client_threads_mutex_`. It sets a `finished` flag, and `reap_finished_clients_locked()` joins and erases it. `stop()` does `shutdown(fd)` to wake blocked reads. |
| Notification broadcast (called from the worker) | `broadcast_notification` | Writes JSON-RPC to every subscriber | `subscribers_mutex_` is held only to snapshot the set, then released before writing. Writes use `send(MSG_DONTWAIT \| MSG_NOSIGNAL)`, so a slow client can't block the worker. Dead fds are removed under the lock. |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Watches MCP server health | The loop only enqueues. `process_events()` swaps the queue out under `event_mutex_` and runs the callbacks on the engine thread. |
| Stdio and SSE reader threads | `transport_stdio.cpp:164`, `transport_sse.cpp:107` | Read child stderr and the SSE stream | Each has its own transport lock (`io_mutex_`, `pending_mutex_`). |
| Cancel poller threads | `inference_c_api.cpp:385` (`CancelFlagBridge`), `interface_factory.cpp:246` (`iface_generate_with_cancel`) | Poll a 10 ms interval and translate an `int` cancel flag into an `atomic<bool>` | Each sets a `done` flag and is joined before the function returns, so it can't outlive its caller. |
| Interrupt observer | `response_generator.cpp:413` (`dispatch_batch_generate`) | Mirrors the engine's `interrupt_flag_` into the C-ABI `int` cancel flag | Same `done` flag plus join pattern. |

The test-only spawn is `MockSSEServer::listen_after_bind` in `transport_sse_test.cpp:98`.

**Concerns I found while reading the bodies**

- **Cancel flag is a plain `int`.** The C ABI is `int*`, so the observer thread writes `cancel_int` (`response_generator.cpp`) while the backend's poller reads `*cancel` concurrently without an atomic. This is a deliberate choice to keep atomics off the `.so` boundary, but in the C++ memory model it is a data race. It is probably benign on current hardware. I'd want it atomic or wrapped in an accessor.
- **Detached async worker.** `run_async_ask` launches a `std::thread` that captures `this`. The body I could see (truncated at line 1201) doesn't show a join or a lifetime guarantee that `ExternalBridge` outlives the worker. I could not confirm that from the index.
- **Lock order.** The index records three ordered two-lock pairs. None appear in opposite orders, so it flags no deadlock. Two of the pairs (`event_mutex_`→`adapter_mutex_` in `health_monitor.cpp:122`, and `auth_mutex_`→`key_mutex_` in `mcp_authorization.cpp:105`) have zero resolved receivers, so I'd treat them as unconfirmed.

**Caveat:** Every thread row is `confidence: medium`, and the index only sees spawn sites matching its built-in primitive patterns. A project-specific spawn helper would be invisible here.