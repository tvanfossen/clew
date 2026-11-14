Ten thread-spawn sites in first-party code (the index's spawn-pattern count, scoped to the primitives it searches), grouped by what they do. Most are guarded by a lock or a join; one has a lifetime gap I could not close from the index.

**Threads that run work off the caller's thread**

| Spawn site | Thread body | Lifetime |
|---|---|---|
| `ExternalBridge::start` (`external_bridge.cpp:796`) | `accept_loop` | Joined in `stop()` |
| `ExternalBridge::accept_loop` (`:945`) | `serve_client` per accepted socket | Owned by `client_threads_`; joined in `stop()` |
| `ExternalBridge::run_async_ask` (`:1158`) | Runs `entropic_run` for an async `entropic.ask` | **Detached** |
| `HealthMonitor::start` (`health_monitor.cpp:92`) | `monitor_loop` | Joined in `stop()` |
| `StdioTransport::open` (`transport_stdio.cpp:164`) | `stderr_reader_loop` | Per transport |
| `SSETransport::open` (`transport_sse.cpp:107`) | `sse_reader_loop` | Per transport |
| `ResponseGenerator::dispatch_batch_generate` (`response_generator.cpp:413`) | Interrupt observer | Joined before return |
| `iface_generate_with_cancel` (`interface_factory.cpp:246`) | Cancel poller | Joined before return |
| `CancelFlagBridge` ctor (`inference_c_api.cpp:385`) | Cancel poller | Joined in its dtor |

The MCP server is the largest group. The accept loop, the per-client serve threads and the health monitor run for the lifetime of a handle. The async-ask worker is the one the caller never waits on.

**What keeps them safe**

1. **Scoped joins for short-lived helpers.** The batch observer and the cancel pollers are created inside one call and joined before it returns. Their captured references (`&cancel_int`, `&done`, `&observer_done`) stay valid for exactly that window.

2. **Owned, joined long-lived threads.** `ExternalBridge::stop()` follows a fixed order: clear `running_`, close the listen fd, join the accept thread, move `client_threads_` out under `client_threads_mutex_`, `shutdown(SHUT_RDWR)` each client fd so blocked `read()`s return, then join each client thread. `~ExternalBridge` calls `stop()`. `HealthMonitor::stop()` sets `running_` with `exchange`, notifies `wake_cv_`, and joins. Both are idempotent.

3. **Locks on shared state.** The index lists 45 distinct lock identities in first-party code. The ones that matter for threading:
   - `tasks_mutex_` (`ExternalBridge`) guards the async task registry. `run_async_ask` writes the terminal state and the sentinel file under it, so an external reader that sees the sentinel also sees the same state.
   - `client_threads_mutex_` guards the client-thread vector.
   - `s_bound_sockets_mu` is a process-wide set that stops two handles binding the same socket path.
   - `subscribers_mutex_` guards the notification fan-out.

4. **Logging is handle-scoped across threads.** Each spawned body installs `HandleLogScope(log_id)` so its logs reach the owning handle's session log.

5. **Cross-thread cancel is designed in.** `entropic_interrupt` is documented thread-safe and works by setting an atomic flag. The C ABI carries only `int*`, so no atomic crosses the `.so` boundary. The poller threads bridge the int to the atomic.

6. **Observer generation.** `cancel_inflight_async_tasks` bumps the observer generation after its poll, so late callbacks from a still-running worker are discarded.

**Gap to check**

`run_async_ask` is `std::thread(...).detach()`-style: nothing joins it, and its lambda captures `this` (the bridge). `stop()` and the destructor do not wait for detached workers. `cancel_inflight_async_tasks` only polls about 1 second (20 × 50 ms) for workers to clear the cancelling state. If an async ask is still inside `entropic_run` after that, and the handle is destroyed, the worker would touch a freed `ExternalBridge` and `tasks_mutex_`. I did not confirm whether `entropic_destroy` drains async tasks through another path, so this is unverified. To settle it, read `entropic_destroy` and check whether it waits on in-flight tasks, or check whether the worker is tracked anywhere for a join. If it is not, the fix is to track the worker and join it in `stop()`, or hold a `shared_ptr` to the bridge state inside the lambda.