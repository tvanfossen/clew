# Q3 — mcp — haiku — run 1

## Answer

**Total threads: 21 (4 first-party + 17 vendored)**

entropic spawns threads through four first-party patterns:

### First-party threads (4):

1. **`accept_loop`** — Background thread accepting external MCP client connections and dispatching them to per-client service threads. Spawned in `src/facade/external_bridge.cpp:796` by `ExternalBridge::start()` (thread id 3).

2. **`HealthMonitor::monitor_loop`** — Background monitoring thread that periodically checks configured servers. Spawned in `src/mcp/health_monitor.cpp:92` by `HealthMonitor::start()` (thread id 9).

3. **`StdioTransport::stderr_reader_loop`** — Background thread that forwards child process stderr to spdlog. Spawned in `src/mcp/transport_stdio.cpp:164` by `StdioTransport::open()` (thread id 10).

4. **`SSETransport::sse_reader_loop`** — Background SSE stream reader thread that processes server-sent events. Spawned in `src/mcp/transport_sse.cpp:107` by `SSETransport::open()` (thread id 16).

### Example function trace:

**`serve_client`** executes in **thread id 3 (accept_loop thread family)**:
- Spawned: `src/facade/external_bridge.cpp:796` (via `ExternalBridge::start`)
- Defined: `include/entropic/mcp/external_bridge.h:988`
- Specifically: `serve_client` runs in a per-client `std::thread` spawned within the `accept_loop` function (see `src/facade/external_bridge.cpp:945-949` where the lambda creates a new thread per accepted connection). It handles JSON-RPC message dispatch for a single connected client.

### Coverage:

- **Source**: 4 of 4 first-party spawn sites indexed; 17 from vendored extern/llama.cpp submodule  
- **Scope**: Whole-repo (2,132 files, covering `.c`, `.cpp`, `.h`, `.hpp`, `.m`, `.md`, `.py` extensions)
- **Build patterns**: Indexed spawn primitives: `std::thread`, `pthread_create`, `xTaskCreate` (FreeRTOS), and Python task patterns
- **Thread membership completeness**: Every first-party spawn site is captured; member_count shown per thread (e.g., `accept_loop` has 5 member functions detected)

## Gaps

None. The index provided complete thread enumeration for the first-party codebase with spawn sites, entry functions, and member detection. Vendored threads are correctly attributed to `extern/llama.cpp` and excluded from first-party counts.
