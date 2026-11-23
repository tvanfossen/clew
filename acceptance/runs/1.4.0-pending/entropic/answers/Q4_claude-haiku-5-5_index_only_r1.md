The index shows nine production spawn sites that run off the caller's thread, plus one in a test mock. Thread-safety rests on a few mechanisms, but the lock-order check is unverified.

**Threads that run off the caller's thread (`src/`)**

| Spawn site | What runs there | Joined or detached |
|---|---|---|
| `ExternalBridge::start` → `accept_loop` (`src/facade/external_bridge.cpp:796`) | Polls the listen socket and accepts MCP clients | Long-lived; stopped via `running_` |
| `ct->thread` in `accept_loop` (`:945`) | One `serve_client` thread per accepted client | Reaped later by `reap_finished_clients_locked()` |
| `run_async_ask` lambda (`:1158`) | Runs `entropic_run` for an async `entropic.ask` | Detached |
| `HealthMonitor::start` → `monitor_loop` (`src/mcp/health_monitor.cpp:92`) | MCP server health checks | Long-lived |
| `StdioTransport::open` → `stderr_reader_loop` (`src/mcp/transport_stdio.cpp:164`) | Drains MCP child-process stderr | Long-lived |
| `SSETransport::open` → `sse_reader_loop` (`src/mcp/transport_sse.cpp:107`) | Reads the SSE stream | Long-lived |
| `ResponseGenerator::dispatch_batch_generate` observer (`src/core/response_generator.cpp:413`) | Mirrors the engine's interrupt flag into the C-ABI int cancel flag | Joined before return |
| `iface_generate_with_cancel` poller (`src/inference/interface_factory.cpp:246`) | Same cancel bridging for the orchestrator | Joined before return |
| `CancelFlagBridge` poller (`src/inference/inference_c_api.cpp:385`) | Same cancel bridging for the C API | Joined in its destructor |

A tenth site, `MockSSEServer::listen_after_bind` (`tests/unit/mcp/transport_sse_test.cpp:98`), is test-only.

**What keeps it safe**

- **Shared registries are mutex-guarded.** `run_async_ask` inserts the task under `tasks_mutex_`, then updates status and writes the completion sentinel under that same lock. Per-client threads go into `client_threads_` under `client_threads_mutex_`.
- **Cancellation uses atomics and polling.** Interrupt and cancel flags are `std::atomic<bool>` with acquire/release ordering. The C-ABI boundary passes a plain `int*` polled every 10 ms, because the design rules forbid `std::atomic` across the `.so` boundary.
- **Helper threads are joined before the caller returns.** The observer and poller threads share stack locals by reference, so their lifetimes are bounded by the call.
- **Each client thread owns its fd.** `serve_client` closes its own fd and sets a `finished` atomic flag. `stop()` calls `shutdown(fd, SHUT_RDWR)` to wake blocked reads.
- **Access is restricted before a thread exists.** `accept_loop` checks `SO_PEERCRED` and closes connections from a different uid before spawning a serve thread.
- **Logging context is carried across threads.** Each spawned thread opens a `HandleLogScope` with the owning handle's `log_id`.
- **Known gap.** The speculative-decoding batch path is not cancellable mid-decode; `dispatch_batch_generate` falls back to the non-cancel entry. This is documented in the code, not a silent failure.

**Lock ordering: not confirmed**

The index records 45 distinct lock identities and three two-lock nestings. All three have zero resolved call sites, so none is confirmed:

- `HealthMonitor::event_mutex_` then `AdapterManager::adapter_mutex_` (in `process_events`)
- `MCPAuthorizationManager::auth_mutex_` then `MCPKeySet::key_mutex_` (in `check_access`, 4 sites)
- `MockSSEServer::mu_` then `adapter_mutex_` (test only)

No pair appears in the opposite order, so the index raises no deadlock risk. But that is absence of evidence, not proof of ordering. Four lock identities are member expressions (`bridge->tasks_mutex_` and similar) that the index does not model, so `ExternalBridge::tasks_mutex_` coverage is partial.

The thread entries are rated medium confidence (spawn sites are matched by pattern, not verified at runtime).