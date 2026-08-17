# Q3 — src — haiku — run 1

## Answer: Threads in Entropic

Entropic runs **9 categories of threads**, with the exact count varying at runtime depending on client connections and async tasks:

### 1. **SSE Reader Thread** (1 instance, if SSE transport is active)
- **Location:** `src/mcp/transport_sse.cpp:107`
- **Function:** `SSETransport::sse_reader_loop()` (line 263)
- **Purpose:** Continuously reads from SSE event stream, parses events, stores JSON-RPC responses by request ID
- **Lifecycle:** Started in `SSETransport::open()`, joined on `close()`

### 2. **Stdio Stderr Thread** (1 instance per spawned child process)
- **Location:** `src/mcp/transport_stdio.cpp:164`
- **Function:** `StdioTransport::stderr_reader_loop()` (line 494)
- **Purpose:** Forwards child process stderr to spdlog WARNING logger; polls every 500ms
- **Lifecycle:** Started in `StdioTransport::open()`, joined on `close()`

### 3. **Health Monitor Thread** (1 instance)
- **Location:** `src/mcp/health_monitor.cpp:92`
- **Function:** `HealthMonitor::monitor_loop()` (line 137)
- **Purpose:** Monitors watched MCP server health, handles reconnection attempts, checks every 500ms
- **Lifecycle:** Started in `HealthMonitor::start()`, joined on `stop()`

### 4. **Response Generator Observer Thread** (ephemeral, 1 per cancellable inference)
- **Location:** `src/core/response_generator.cpp:413`
- **Purpose:** Polls interrupt flag at 10ms intervals during batch generation, bridges engine interrupt to C ABI cancel_int parameter
- **Lifecycle:** Spawned at start of `dispatch_batch_generate()`, joined before return
- **Lifetime:** Microseconds to seconds (as long as inference runs)

### 5. **Inference C API Poller Thread** (ephemeral, 1 per C API inference call)
- **Location:** `src/inference/inference_c_api.cpp:385` (class `CancelFlagBridge`)
- **Purpose:** Bridges int* cancel_flag (C ABI) to std::atomic<bool> for backend; polls every 10ms
- **Lifecycle:** Spawned in constructor, joined in destructor

### 6. **Interface Factory Poller Thread** (ephemeral, 1 per orchestrator generate call)
- **Location:** `src/inference/interface_factory.cpp:246`
- **Purpose:** Similar to C API poller; bridges int* cancel to atomic<bool> during inference
- **Lifecycle:** Spawned inline during generate, joined before return

### 7. **Accept Thread** (1 instance, if external MCP bridge is running)
- **Location:** `src/facade/external_bridge.cpp:796`
- **Function:** `ExternalBridge::accept_loop()` (line 917)
- **Purpose:** Listens on Unix domain socket, accepts client connections, spawns per-client threads
- **Lifecycle:** Started in `ExternalBridge::start()`, joined in `ExternalBridge::stop()`

### 8. **Per-Client Serve Threads** (variable: 1 per connected MCP client)
- **Location:** `src/facade/external_bridge.cpp:945`
- **Function:** `ExternalBridge::serve_client()` (line 988)
- **Purpose:** Reads JSON-RPC requests from client socket, dispatches to MCP tools (initialize, tools/list, tools/call, entropic.ask, entropic.status, etc.)
- **Lifecycle:** Spawned in `accept_loop()` per connection, joined in `ExternalBridge::stop()`

### 9. **Async Ask Worker Threads** (variable: 1 per async entropic.ask request)
- **Location:** `src/facade/external_bridge.cpp:1158`
- **Function:** Lambda in `ExternalBridge::run_async_ask()` calls `entropic_run()`
- **Purpose:** Executes inference asynchronously, reports progress via MCP notifications, detached (not joined)
- **Lifecycle:** Spawned in `run_async_ask()`, detached immediately

---

## Example: Tracing `handle_status()`

**Function choice:** `handle_status()` at `src/facade/external_bridge.cpp:295`

**Execution thread:** **Per-client serve thread** (one per connected MCP client)

**Call chain:**
```
Per-client serve_client(client_fd) [external_bridge.cpp:988]
  → read JSON-RPC request from socket
  → dispatch(request_json, client_fd) [external_bridge.cpp:1038]
    → dispatch_tool(...) [external_bridge.cpp:570]
      → handle_status(handle) [external_bridge.cpp:295]
        → entropic_context_count(handle, &count) [facade/entropic.cpp:2739]
          → handle->engine->message_count() [lock-free atomic read]
        → entropic_metrics_json(handle, &mjson) [facade/entropic.cpp:2881]
          → queries engine metrics asynchronously
        → returns JSON tool result to client
```

**Thread safety:** `handle_status()` acquires no locks on the main engine (metrics queries are lock-free). The per-client serve thread runs concurrently with the async ask worker threads and can be interrupted by the accept thread only during socket operations.

---

## Coverage

**Codebase scope:**
- **Source files analyzed:** 112 files (`.cpp` and `.h` in `src/`)
- **Lines of code:** 3,276 LOC in source (excluding extern/llama.cpp submodule)
- **Threading code coverage:** All 9 thread spawn sites identified and traced
  - 6 long-lived infrastructure threads (SSE, stderr, health monitor, accept)
  - 3 per-request threads (generator observer, pollers, async ask worker)

**Threads per layer:**
- **MCP Transport layer:** 2 (SSE reader, stdio stderr)
- **Health/Reconnection:** 1 (monitor)
- **Inference execution:** 3 (observer, C API poller, interface factory poller) — ephemeral during generation
- **Socket I/O:** 1 accept + N per-client serves
- **Async task execution:** M async ask workers (detached)

---

## Gaps

- **Llama.cpp internal threads:** The `extern/llama.cpp` submodule contains additional threading (at least in server-mode build), but that submodule's code is excluded per the benchmark scope (entropic source-only). Llama.cpp's own threading is transparent to entropic's management layer.
- **Memory ordering semantics:** Could not fully verify all std::memory_order specifications without running dynamic analysis (all uses appear correct: acquire/release patterns for flags, relaxed for metrics).
- **Exact async task cardinality:** The number of async ask workers depends on client request rate and task cleanup; no static bound enforced beyond 15-minute expiration (`src/facade/external_bridge.cpp:1220`).
