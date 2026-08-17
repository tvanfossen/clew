# Q3 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll answer this question using the index to discover threads in entropic, then trace a specific function to determine which thread executes it.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"thread spawn create","note":"No matching symbols for 'thread spawn create'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative …

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"threads":[{"id":1,"name":"Processor._worker","kind":"task","entry":"_worker","source":"ast_spawn","confidence":"medium","member_count":1,"spawn_file":"extern/llama.cpp/examples/llama-eval/llama-eval.py","spawn_line":13…

**Reasoning.** Now let me get details on one of the first-party threads to trace which functions execute in it:

### 3. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"accept_loop","subject_kind":"function","name":"accept_loop","rowid":9113,"signature":"void entropic::ExternalBridge::accept_loop()","file":"include/entropic/mcp/external_bridge.h","line_start":917,"line_end":…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"serve_client","subject_kind":"function","name":"serve_client","rowid":9114,"signature":"void entropic::ExternalBridge::serve_client(int client_fd)","file":"include/entropic/mcp/external_bridge.h","line_start"…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** __unparsedToolInput
- **got ⚠ error:** <tool_use_error>InputValidationError: mcp__doxyguard-db__dossier was called with input that could not be parsed as JSON. You sent (first 115 of 115 bytes): {"subject": [monitor_loop, stderr_reader_loop, sse_reader_loop],…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["monitor_loop","stderr_reader_loop","sse_reader_loop"],"results":[{"subject":"monitor_loop","subject_kind":"function","name":"monitor_loop","rowid":17470,"signature":"voi…

**Reasoning.** ## Answer

**Total threads: 21 (4 first-party + 17 vendored)**

entropic spawns threads through four first-party patterns:

### First-party threads (4):

1. **`accept_loop`** — Background thread accepting external MCP client connections and dispatching them to per-client service threads. Spawned in `src/facade/external_bridge.cpp:796` by `ExternalBridge::start()` (thread id 3).

2. **`HealthMonitor::monitor_loop`** — Background monitoring thread that periodically checks configured servers. Spawned in `src/mcp/health_monitor.cpp:92` by `HealthMonitor::start()` (thread id 9).

3. **`StdioTranspo

---

## Final answer as submitted

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
