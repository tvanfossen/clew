Ten spawn sites in first-party code run off the caller's thread. Each one is a `std::thread` or pthread the index resolved to a file and line. Most are in the MCP bridge and transports, plus a few cancellation pollers in inference. Safety rests on three mechanisms: mutexes guarding shared state, atomics for flags, and join-before-return for scoped helpers. One path does not join and needs a check.

**Background threads (the spawn sites)**

| Thread | Where | Why it runs off-thread | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `src/facade/external_bridge.cpp:796` (`start`) | Blocks on `accept` for MCP clients | Polls with a 500ms timeout and checks `running_`. `stop()` joins it. Each accepted fd is checked with `SO_PEERCRED`, so a cross-uid connection is closed before a thread is spawned. |
| Per-client `serve_client` thread | `external_bridge.cpp:945` | One per connected client | Registered in `client_threads_` under `client_threads_mutex_`. Finished threads are reaped. `stop()` calls `shutdown(SHUT_RDWR)` to wake blocked reads, then joins. |
| `run_async_ask` worker | `external_bridge.cpp:1158`, detached at `:1222` | Runs `entropic_run` for `entropic.ask` | Task map is guarded by `tasks_mutex_`. The sentinel file is written under that lock, before the completion notification fires. |
| `HealthMonitor::monitor_loop` | `src/mcp/health_monitor.cpp:92` | Periodic MCP server health checks | `stop()` joins it at `:108`. Shared state sits behind `event_mutex_`, `watched_mutex_` and `wake_mutex_`. |
| `StdioTransport::stderr_reader_loop` | `src/mcp/transport_stdio.cpp:164` | Drains child-process stderr | Joined in `close` at `:219`. Writes to the stdio channel go through `io_mutex_`. |
| `SSETransport::sse_reader_loop` | `src/mcp/transport_sse.cpp:107` | Reads the SSE stream | Joined at `:139`. Pending requests are guarded by `pending_mutex_`. |
| Cancel pollers | `inference_c_api.cpp:385` (`CancelFlagBridge`), `interface_factory.cpp:246` (`iface_generate_with_cancel`), `response_generator.cpp:413` (`dispatch_batch_generate`) | Turn a int or atomic cancel flag into a value the backend polls, roughly every 10ms | Each is a scoped helper with a `done` atomic and is joined before the function returns. The observer captures locals by reference, which is safe only because of that join. |

**The unsafe-looking path: the detached `run_async_ask` worker**

- The worker is detached (`external_bridge.cpp:1222`) and captures `this` and `handle_`.
- `stop()` (`:826`) does not wait for it. It joins the accept thread and the per-client threads only.
- So if the bridge is destroyed while an async ask is still running, the worker can use freed memory. I did not verify whether the destructor or `entropic_destroy` waits on in-flight tasks; I only read `stop()`. This is the one place where "what keeps it safe" is not confirmed. Check the destructor and `entropic_destroy` before relying on it.

**Other things I noticed**

- **Plain `int` cancel flag.** `dispatch_batch_generate` writes `cancel_int` from its observer thread. `iface_generate_with_cancel`'s poller reads it through a pointer, with no atomic. That is a data race under the C++ memory model, even if benign in practice. I did not check how the backend reads it.
- **Exception safety of pollers.** In `iface_generate_with_cancel` and `dispatch_batch_generate`, if `generate` throws, the joinable poller or observer is never joined. Destroying a joinable `std::thread` calls `std::terminate`. I did not check whether `generate` can throw.
- **Lock ordering.** The index reports three two-lock nestings. None is taken in opposite orders, so it flags no deadlock. But all three have unresolved receivers, so I would not call them confirmed. The pairs are `event_mutex_` → `adapter_mutex_`, and `auth_mutex_` → `key_mutex_`.

The index counts 10 first-party spawn sites and 45 distinct lock identities. The count covers only the spawn primitives this build's patterns match.