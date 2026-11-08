Entropic has ten background-thread spawn sites in its own code, all `std::thread`/pthread and all found by the index's spawn-pattern matcher. The index sees no spawns outside those patterns, so this is a count of matched sites, not proof of none elsewhere. Safety comes from a handful of repeated patterns: a shared lock per object, atomics for flags, joins before return, and socket shutdown to unblock readers.

**Threads that run off the caller's thread**

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` | Polls the listen socket every 500 ms, checks peer uid, and spawns one thread per client. |
| Per-client `serve_client` thread | `accept_loop` | Serves one external MCP client. |
| `ExternalBridge::run_async_ask` worker | `run_async_ask` (`external_bridge.cpp:1158`) | Runs `entropic_run` for an async ask and updates task state. |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` | Checks watched MCP servers every 500 ms and queues health events. |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` | Drains a child process's stderr. |
| `SSETransport::sse_reader_loop` | `SSETransport::open` | Reads the SSE stream. |
| `ResponseGenerator::dispatch_batch_generate` observer | that function | Short-lived; mirrors the interrupt flag into the C-ABI cancel int during a batch call. |
| `iface_generate_with_cancel` poller | that function | Short-lived; mirrors the cancel int into an atomic during a batch call. |
| `CancelFlagBridge` poller | its constructor | Same 10 ms cancel-bridge pattern used in `entropic_inference_generate_with_cancel`. |
| `MockSSEServer` listener | test code only | Test fixture. |

**What keeps it safe**

- **Per-object mutexes, with the lock held only for short critical sections.** `tasks_mutex_` guards the async task map. `client_threads_mutex_` guards the client list. `watched_mutex_` and `wake_mutex_` guard `HealthMonitor`. The index lists about 45 distinct lock identities, all in this repo.
- **Callbacks run on the engine thread.** `HealthMonitor::process_events` swaps the event queue out under `event_mutex_`, then invokes the status callback after releasing the lock. The index's own doc comment says it runs on the engine thread.
- **Atomics for cross-thread flags.** `running_`, `finished`, `done`, `observer_done`, and the cancel flags are atomics with acquire/release ordering. The cancel int is kept as an `int*` so no `std::atomic` crosses the `.so` boundary.
- **Join before return.** The batch-cancel poller and observer are joined before the function returns, so their by-reference captures of locals stay valid. `HealthMonitor::stop` sets `running_` to false, notifies the condition variable, then joins.
- **Ordered shutdown in `ExternalBridge::stop`.** It clears `running_` and closes the listen socket, joins the accept thread so no new clients spawn, calls `shutdown(SHUT_RDWR)` on each client fd to wake blocked reads, then joins the client threads. Only after that does it release the bound-socket claim.
- **Per-client cleanup and access control.** Each client thread closes its own fd and sets `finished`, and `reap_finished_clients_locked` joins and erases them. Every accepted fd is checked with `SO_PEERCRED` before a serve thread is created (gh#34).
- **Log routing across threads.** Spawned threads create a `HandleLogScope` with the owning handle's `log_id` (gh#59), so their logs land in the right session.
- **Sentinel ordering.** `run_async_ask` writes the per-task sentinel file while holding `tasks_mutex_`, before the progress notification fires (issue #12).

**Gaps and risks I could not settle from the index**

1. **The async-ask worker is detached.** `run_async_ask` starts a `std::thread` with no stored handle and captures `this`. `ExternalBridge::stop` drains only the client threads and never waits for it. If the bridge is destroyed while an ask is running, the worker could touch freed state. I did not find a join or a lifetime guard for it in the index, so treat this as a likely lifetime bug to verify in the source.
2. **Lock-order check.** The index records three two-lock nestings and no reverse pair, so it shows no deadlock. However, all three have `resolved_sites: 0`, so none of them is confirmed. The lock-hold data for `HealthMonitor` (`event_mutex_` → `adapter_mutex_` in `process_events`) and `MCPAuthorizationManager` (`auth_mutex_` → `key_mutex_` in `check_access`) are the ones to verify.
3. **Partial bodies.** The index returned no bodies for the stdio and SSE reader loops or for `CancelFlagBridge`'s destructor, so I could not confirm their stop and join logic. Two lock identities, `bridge.tasks_mutex_` and `s_ggml_log_mu`, have low identity confidence.