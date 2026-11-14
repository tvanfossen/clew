Ten thread spawn sites are in the first-party code, per the index's `thread_patterns` matching. Only `pthread`/`std::thread`-style spawns are matched, so a custom spawn helper would not show up. The safety mechanisms are mostly one of three things: join-before-return, atomics for flags, or a mutex held only around a queue or map.

| Spawn site | Thread body | What it does | What keeps it safe |
|---|---|---|---|
| `ResponseGenerator::dispatch_batch_generate` (`src/core/response_generator.cpp:413`) | `observer` | Mirrors the engine's `interrupt_flag_` into the C-ABI `int` cancel flag during a batch generate | `observer_done` is an atomic. The thread captures `&cancel_int` and `&observer_done` by reference, which is valid because the caller joins it before returning. |
| `iface_generate_with_cancel` (`src/inference/interface_factory.cpp:246`) | `poller` | Polls the `int*` cancel pointer every 10 ms and sets a `std::atomic<bool>` for the orchestrator | Same pattern: `done` atomic, joined before `*result_json` is set. The `int*` never crosses the `.so` boundary as an atomic. |
| `CancelFlagBridge` ctor (`src/inference/inference_c_api.cpp:385`) | `poller_` | Same bridge for the `entropic_inference_generate_with_cancel` C entry | `done_` and `cancel_` atomics. A null cancel pointer means no thread is started. |
| `ExternalBridge::run_async_ask` (`src/facade/external_bridge.cpp:1158`) | detached lambda | Runs `entropic_run` for an async `entropic.ask` and publishes the result | Task map is written only under `tasks_mutex_`. The sentinel file is written under that same lock, before the progress notification goes out. `HandleLogScope` carries the log ID into the thread. |
| `ExternalBridge::accept_loop` (`:796`) | accept loop | `poll` with a 500 ms timeout so it can see shutdown; checks `SO_PEERCRED` on each fd | `running_` atomic. Cross-uid connections are closed before a serve thread exists. |
| `ct->thread` per client (`:945`) | `serve_client` | Serves one MCP client | `ClientThread` is owned by `client_threads_` under `client_threads_mutex_`. The thread sets an atomic `finished` flag, which `reap_finished_clients_locked()` uses to join and erase. |
| `HealthMonitor::monitor_loop` (`src/mcp/health_monitor.cpp:92`) | monitor | Health checks on MCP servers; pushes events onto a queue | Producer side takes `event_mutex_` to append. `process_events()` swaps the queue out under that lock and then runs `status_callback_` after releasing it. Callbacks therefore run on the engine thread, not the monitor thread. |
| `StdioTransport::stderr_reader_loop` (`src/mcp/transport_stdio.cpp:164`) | stderr reader | Drains child stderr | `connected_` atomic; `io_mutex_` guards I/O. |
| `SSETransport::sse_reader_loop` (`src/mcp/transport_sse.cpp:107`) | SSE reader | Reads the event stream | `running_` and `connected_` atomics; `pending_mutex_` guards pending requests. `open()` sleeps 500 ms and then checks `connected_`. |
| `ModelOrchestrator`/test helpers | `listen_after_bind` (test), `observer`, etc. | Test mock server and similar helpers | Test-only; not part of the runtime story. |

**What the index shows about lock ordering**

- 45 distinct first-party lock identities; `ExternalBridge` has the most (`tasks_mutex_`, `subscribers_mutex_`, `client_threads_mutex_`, `s_bound_sockets_mu`).
- The index reports 3 two-lock nestings. None of them is confirmed: all three have `resolved_sites=0`, meaning the receiver of the call was never verified.
- The `event_mutex_` → `adapter_mutex_` nesting attributed to `HealthMonitor::process_events` looks like a false positive. The body I read holds only `event_mutex_` during the swap and calls the callback after releasing it.
- No two sites take the same pair in opposite orders, so there is no deadlock candidate in the index's data.

**What I did not verify**

- I did not read the `run_async_ask` body past line 1201, so I have not confirmed that the thread is detached. The lambda captures `this` and `handle_`, so its safety depends on the bridge outliving it, which I have not checked.
- I did not check that `HealthMonitor::stop()` joins `monitor_thread_`.
- I did not check the body of `write_sentinel` for further locking under `tasks_mutex_`.

The conclusion is that the cancel bridges and the health monitor are sound by construction, while the `ExternalBridge` lifetime and shutdown paths need a read of `stop()`, the detach point, and `write_sentinel` before I would sign off on them.