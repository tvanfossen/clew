**Short answer:** Ten thread spawn sites in first-party code (all `std::thread`/pthread, medium confidence). Shared state is guarded by named mutexes and atomics, and each spawned thread is joined or reaped by its owner. Two things I could not confirm from the index: the detached async-ask thread's lifetime, and one plain-`int` cancel flag.

**Threads that run off the caller's thread**

| Area | Spawn site | Role |
|---|---|---|
| External MCP bridge | `ExternalBridge::start` → `accept_loop` | Accepts socket clients, polls every 500 ms |
| External MCP bridge | `accept_loop` → per-client thread | `serve_client` per connection |
| External MCP bridge | `ExternalBridge::run_async_ask` | Detached thread that runs `entropic_run` for `entropic.ask` |
| Health | `HealthMonitor::start` → `monitor_loop` | Background health and reconnect checks |
| MCP stdio | `StdioTransport::open` → `stderr_reader_loop` | Drains child-process stderr |
| MCP SSE | `SSETransport::open` → `sse_reader_loop` | Reads the event stream |
| Inference cancel | `iface_generate_with_cancel` poller, `CancelFlagBridge` poller | Bridges a C `int*` cancel flag to an atomic |
| Generation | `ResponseGenerator::dispatch_batch_generate` observer | Mirrors `interrupt_flag_` into the cancel `int` for one call |
| Tests | `MockSSEServer` listener | Test-only |

**What keeps them safe**

1. **Shared task state is behind one mutex.** `run_async_ask` takes `tasks_mutex_` to create the queued entry and again to store the terminal state. It writes the sentinel file inside that same lock, so an external monitor that sees the sentinel can immediately read the same state.
2. **Atomics for flags.** `running_`, `connected_`, the cancel flags, and `interrupt_flag_` (`std::atomic<bool>`, `engine.h:1415`) are all atomics. The pollers use acquire/release on their `done` flags.
3. **Owned lifetimes.** `ExternalBridge::stop()` clears `running_`, closes the listen socket, joins the accept thread, `shutdown(SHUT_RDWR)`s each client fd to wake blocking reads, then joins each client thread. `accept_loop` also reaps finished clients under `client_threads_mutex_`.
4. **Access control at accept.** Every accepted fd must pass `peer_uid_matches` (SO_PEERCRED) before a serve thread is spawned.
5. **Log scope is propagated.** Each thread body opens `HandleLogScope(log_id)`, so logs from worker threads land in the owning handle's session log.
6. **Lock ordering.** The index sees three two-lock nestings: `auth_mutex_`→`key_mutex_`, `event_mutex_`→`adapter_mutex_`, and `mu_`→`adapter_mutex_` in a test. None is taken in reverse, so there is no deadlock pair. However, all three have `resolved_sites=0`, so I would not call the ordering verified.

**Gaps and risks**

- **`run_async_ask` is detached.** It captures `this` and `handle_`, and I found no join or tracking for it in the index. If the bridge is destroyed while a task is running, that is a use-after-free. Check whether `stop()` or the destructor waits for these tasks; the index does not show it.
- **Plain `int` cancel flag.** In `dispatch_batch_generate`, the observer thread writes `cancel_int` (a plain `int`) while the backend reads it through `&cancel_int` on the calling thread. That is a data race under the C++ memory model, even though the code is meant to keep the C ABI `int*`-only. The `iface_generate_with_cancel` poller has the same shape: it reads `*cancel` non-atomically. This is the item I would check first.
- **Coverage.** The thread count covers only the spawn primitives this index's patterns match. Other spawn helpers would not appear.