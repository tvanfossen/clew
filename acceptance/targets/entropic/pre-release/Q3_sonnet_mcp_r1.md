# Q3 — mcp — sonnet — run 1

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
