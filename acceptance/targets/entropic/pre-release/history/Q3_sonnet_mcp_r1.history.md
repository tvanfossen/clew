# Q3 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"threads":[{"id":1,"name":"Processor._worker","kind":"task","entry":"_worker","source":"ast_spawn","confidence":"medium","member_count":1,"spawn_file":"extern/llama.cpp/examples/llama-eval/llama-eval.py","spawn_line":13…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
### 3. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"HealthMonitor::monitor_loop","subject_kind":"thread","id":9,"name":"HealthMonitor::monitor_loop","kind":"pthread","entry":"monitor_loop","source":"ast_spawn","confidence":"medium","member_count":5,"spawn_file…

- **got:** {"kind":"dossier","subject":"HealthMonitor::start","found":false,"note":"No dossier for 'HealthMonitor::start' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** kind=function
- **got:** {"subject":"monitor_loop","subject_kind":"function","name":"monitor_loop","rowid":17470,"signature":"void entropic::HealthMonitor::monitor_loop()","file":"include/entropic/mcp/health_monitor.h","line_start":137,"line_end…

**Reasoning.** Now let me check coverage stats for the "how much of the codebase" part.

### 5. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got ⚠ error:** Error executing tool index: index(action='status') does not take a target, and '~/ddb-targets/entropic' was supplied. Refusing rather than ignoring it, because this action reports on the DERIVED target and on where that …

### 6. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got:** {"build_version":50,"symbol_rows":58277,"calls":{"rows":67933,"logical_pairs":57462,"row_inflation":1.1822,"pairs_without_nonfuzzy":1,"pairs_without_nonfuzzy_share":0,"rows_by_confidence":{"exact":48471,"resolved":19461,…

**Reasoning.** ## Threads entropic runs

The index's `threads` layer records **21 thread rows total**, but 17 of those are spawned inside the vendored `extern/llama.cpp` submodule, not by entropic itself. Filtering to first-party spawn sites (`origin.first_party` = 4), **entropic itself spawns 4 threads**:

| Thread (entry) | Spawn site | Kind |
|---|---|---|
| `ExternalBridge::accept_loop` | `src/facade/external_bridge.cpp:796` (in `ExternalBridge::start`) | pthread, 5 members |
| `HealthMonitor::monitor_loop` | `src/mcp/health_monitor.cpp:92` (in `HealthMonitor::start`) | pthread, 5 members |
| `StdioTrans

---

## Final answer as submitted

## Threads entropic runs

The index's `threads` layer records **21 thread rows total**, but 17 of those are spawned inside the vendored `extern/llama.cpp` submodule, not by entropic itself. Filtering to first-party spawn sites (`origin.first_party` = 4), **entropic itself spawns 4 threads**:

| Thread (entry) | Spawn site | Kind |
|---|---|---|
| `ExternalBridge::accept_loop` | `src/facade/external_bridge.cpp:796` (in `ExternalBridge::start`) | pthread, 5 members |
| `HealthMonitor::monitor_loop` | `src/mcp/health_monitor.cpp:92` (in `HealthMonitor::start`) | pthread, 5 members |
| `StdioTransport::stderr_reader_loop` | `src/mcp/transport_stdio.cpp:164` (in `StdioTransport::open`) | pthread, 4 members |
| `SSETransport::sse_reader_loop` | `src/mcp/transport_sse.cpp:107` (in `SSETransport::open`) | pthread, 4 members |

The other 17 (e.g. `httplib::ThreadPool::worker`, `server_http_context::listen_after_bind`, `ma_thread_create__posix`/`__win32`, various Python `threading.Thread`/`asyncio` spawns in test/bench scripts) all originate under `extern/llama.cpp` — vendored, not entropic's own code — per `origin.external_roots: ["extern/llama.cpp"]`.

## Example: which thread executes `monitor_loop`

`entropic::HealthMonitor::monitor_loop()` is defined at `include/entropic/mcp/health_monitor.h:137-155` (body in `src/mcp/health_monitor.cpp:137-155`). It is itself the entry function of thread id 9, spawned by `HealthMonitor::start` at `src/mcp/health_monitor.cpp:92`.

Its body (`src/mcp/health_monitor.cpp:137-155`):
- Runs a polling loop (500ms interval) while `running_` is true.
- Holds `watched_mutex_` (`class:HealthMonitor`, lines 142-149) around iterating `watched_` and calling `check_server(name, entry)` (line 146) when an entry's `next_action` is due.
- Holds `wake_mutex_` (lines 151-154) while waiting on `wake_cv_.wait_for(...)`.
- Calls `check_server` (`src/mcp/health_monitor.cpp` — resolved callee, rowid 17471).

So: **`monitor_loop` runs entirely on the `HealthMonitor::monitor_loop` thread (thread id 9)** — a dedicated background pthread started by `HealthMonitor::start`, distinct from whatever thread calls `start()`.

## Coverage

Per `index(action=stats)`: the index covers **482 indexed files** (418 with symbols), of which **1,237 are marked external** (the `extern/llama.cpp` submodule, tracked but reported separately from first-party figures). Substantive first-party files: 310, barren: 4 (barren_ratio 1.3%). Thread/lock layers are populated: 21 thread rows, 47 thread-membership rows, 103 locks, 403 lock acquisitions, 1,803 critical-section calls, 7 external boundaries — all queried live in this answer.

## Gaps

- I did not verify whether `check_server` (the one callee of `monitor_loop`) itself acquires additional locks or spawns further work — that would need a follow-up `dossier(check_server)` call, which I skipped since one thread's execution path was sufficient to answer the question.
- Thread `confidence` is reported as `"medium"` for all 21 rows (AST-based spawn-pattern detection, not a guaranteed-exhaustive enumeration) — so a spawn primitive outside the indexed pattern set (e.g. an unrecognized wrapper) would not show up here at all; I have no way to positively rule that out from the index alone.
- I did not separately confirm entropic's total first-party source-file count outside the index's own bookkeeping (it reports 482 indexed + 1,237 external against whatever the full working tree contains); I'm relying on the index's own coverage figures rather than an independent file count.
