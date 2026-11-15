The spawn sites are all in the MCP transports, the external bridge, and the inference cancel path. Five of them (the four background loops plus the async-ask worker) can outlive the call that started them. The index finds 10 spawn sites in first-party code, and I did not read a vendored dependency. Each one's safety comes from a mix of mutexes, atomics, and join-before-return.

**Threads that run off the caller's thread**

| Spawn site | Thread | Lifetime | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::start` → `accept_loop` (`external_bridge.cpp:796`) | Accept thread | Joined in `stop()` | `running_` is an atomic flag; `client_threads_` is guarded by `client_threads_mutex_`. `stop()` clears `running_`, closes the listen fd, and joins the accept thread before touching clients. |
| `accept_loop` → per-client thread (`:945`) | One per connected client | Joined in `stop()` | Each client thread closes its own fd and sets `finished`. `stop()` calls `shutdown(SHUT_RDWR)` to wake blocked reads, then joins. Connections are gated by `SO_PEERCRED`, so a different uid is closed before a thread is spawned. |
| `ExternalBridge::run_async_ask` (`:1158`) | Detached worker that runs `entropic_run` for `entropic.ask` | **Detached** (`.detach()` at `:1222`) | `tasks_mutex_` guards the task registry. The result and the sentinel file are written under that lock, before the progress notification fires. |
| `HealthMonitor::start` → `monitor_loop` (`health_monitor.cpp:92`) | Health poller | Joined in `stop()` | Event queue is guarded by `event_mutex_`. `process_events()` swaps the queue out under the lock, then runs callbacks on the engine thread with the lock released. |
| `StdioTransport::open` → `stderr_reader_loop` (`:164`) | stderr reader | Joined on close | `io_mutex_` guards I/O. |
| `SSETransport::open` → `sse_reader_loop` (`:107`) | SSE reader | Joined at `:139` | `pending_mutex_` guards the pending-request map. |
| `ResponseGenerator::dispatch_batch_generate` → `observer` (`response_generator.cpp:413`) | Short-lived interrupt mirror | Joined before return | Captures the flag by reference, but it is joined before the locals go out of scope. The atomic `interrupt_flag_` is read with acquire ordering. |
| `iface_generate_with_cancel` → `poller` (`interface_factory.cpp:246`) | Short-lived cancel poller | Joined before return | Same join-before-scope pattern. |
| `CancelFlagBridge` → `poller_` (`inference_c_api.cpp:385`) | Cancel poller | Joined in destructor (`:403`) | RAII wrapper; the cancel state is an atomic. |

Two patterns cover most of this. Short-lived pollers always join before their stack variables die, so capturing by reference is safe. The cancel flag crosses the C ABI as a plain `int*` and is bridged to an `atomic<bool>` on the other side, so no C++ atomics cross the `.so` boundary.

**Lock ordering**

The index shows three two-lock nestings, all with `resolved_sites=0`, so none is confirmed.
- `HealthMonitor::event_mutex_` → `AdapterManager::adapter_mutex_` (in `process_events`)
- `MCPAuthorizationManager::auth_mutex_` → `MCPKeySet::key_mutex_` (in `check_access`)
- `MockSSEServer::mu_` → `adapter_mutex_` (test code)

No pair appears in opposite order, so I see no deadlock risk from the index alone.

**Gap I did not close**

`run_async_ask` is detached and captures `this` (the `ExternalBridge`) and `handle_`. `stop()` joins only the accept and client threads, not the async workers. I found no in-flight counter or join for them. The only cancellation I saw is `cancel_inflight_async_tasks`, which runs on `entropic.context_clear`. If an `ExternalBridge` is destroyed while an async ask is still running, that detached thread dereferences a dead object. I did not read the destructor path or `entropic_destroy` to see whether something else waits for those workers. That is the first thing to check. The quick test is to start an async ask and destroy the handle while it runs, under ThreadSanitizer or ASan.