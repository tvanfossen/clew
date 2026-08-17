# Q3 — src — sonnet — run 1

## Answer

**Thread model:** entropic is not a fixed-N-thread program — it's one main thread plus a small number of long-lived worker threads whose count depends on runtime config (how many MCP servers it connects to), plus several short-lived (transient) threads spawned per-request.

### Long-lived threads

1. **Main thread** — entry point `src/cli/main.cpp`.
2. **Health-monitor thread** — one per process. `ServerManager` owns a single `HealthMonitor` (`src/mcp/server_manager.cpp:509`), and `HealthMonitor::start()` spawns `monitor_thread_` running `HealthMonitor::monitor_loop` (`src/mcp/health_monitor.cpp:90-93`).
3. **Per-MCP-server transport reader threads** — one per connected external MCP server, chosen by `ServerManager`'s transport factory (`src/mcp/server_manager.cpp:578` → `SSETransport`, `:584` → `StdioTransport`):
   - `StdioTransport::open()` spawns `stderr_thread_` running `StdioTransport::stderr_reader_loop` (`src/mcp/transport_stdio.cpp:163-164`).
   - `SSETransport::open()`-equivalent spawns `sse_reader_thread_` running `SSETransport::sse_reader_loop` (`src/mcp/transport_sse.cpp:106-107`).

### Short-lived (transient) threads, spawned per operation

4. **Cancel-flag poller in `ResponseGenerator::dispatch_batch_generate`** — spawns an `observer` thread that polls an interrupt flag every 10ms and mirrors it into an `int` the backend polls (`src/core/response_generator.cpp:379,408-418`).
5. **Cancel-flag poller in `iface_generate_with_cancel`** — same pattern, spawns `poller` (`src/inference/interface_factory.cpp:232-253`).
6. **`CancelFlagBridge`** (RAII, used by the C ABI batch-generate entry point) — spawns `poller_` in its constructor, joined in its destructor (`src/inference/inference_c_api.cpp:376-406`).
7. **Async-ask worker** — `ExternalBridge::run_async_ask` spawns and immediately `.detach()`es a thread that runs the engine (`entropic_run`) for the async `entropic.ask` MCP tool, then writes a sentinel file and broadcasts a `notifications/progress` message (`src/facade/external_bridge.cpp:1142-1222`).

### Example: which thread executes a function

`HealthMonitor::monitor_loop` — this is the function body executed by the **health-monitor thread** created in `HealthMonitor::start()` (`src/mcp/health_monitor.cpp:92-93`, spawned via `std::thread(&HealthMonitor::monitor_loop, this)`). It is not run on the main thread or on any transport thread; it runs continuously for the process lifetime once `start()` is called, watching connection health independently of the per-server reader threads.

## Coverage

This answer is based on a targeted grep for `std::thread`, `pthread_create`, `std::async`, and `.detach()` across `src/` and `include/` (92 `.cpp` files, ~39.5k lines in `src/`), excluding `tests/`. I read the immediate spawn sites and enough surrounding code to identify the enclosing function/class and, for `HealthMonitor` and the transports, traced ownership back to `server_manager.cpp` to establish "one health monitor, one transport thread per configured MCP server." I did **not** exhaustively read every one of the 92 source files, so:

## Gaps

- I did not verify there are no other spawn mechanisms I might have missed (e.g., a thread pool, `libuv`/`asio` executors, or threads created inside third-party/vendored code under `extern/` or a bundled `llama.cpp`, which I explicitly excluded from the grep and did not search).
- I did not check build/CMake files for whether any of these compilation units are conditionally excluded (e.g., SSE transport behind a feature flag), so the actual thread count on a given running instance could differ from "all sites listed."
- I did not confirm whether `llama_cpp_backend.cpp`'s use of `std::thread::hardware_concurrency()` (`src/inference/llama_cpp_backend.cpp:332`) is used only to size a thread-pool *inside* llama.cpp (vendored/external) rather than spawning entropic-owned threads — I treated it as sizing only, not a spawn site, but did not trace into the backend library to confirm.
