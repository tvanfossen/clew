I have enough to answer. One caveat worth stating up front: the index's thread layer is derived from AST spawn-site pattern matching (`source: ast_spawn`, `confidence: medium`) — it's a good map of `std::thread`/pthread call sites this build knows how to recognize, not a certified enumeration of every concurrent path in the binary.

## What runs off the caller's thread

The index resolves five first-party thread rows (a sixth, `listen_after_bind`, is a test-fixture mock in `tests/unit/mcp/transport_sse_test.cpp` and not production code):

**1. `ExternalBridge::accept_loop`** (`src/facade/external_bridge.cpp:917`, spawned from `ExternalBridge::start`)
A background accept loop that `poll()`s the listen socket and, per connection, spawns *another* thread inline (`ct->thread = std::thread([...]{ serve_client(...); })`) after checking `SO_PEERCRED` via `peer_uid_matches`. So this is actually two thread tiers: one long-lived accept thread, plus one short-lived per-client serve thread for each connection. Safety: the per-client thread closes its own fd and flips an atomic `finished` flag on exit rather than touching the shared list directly; the accept thread then reaps finished entries under `client_threads_mutex_` (RAII `lock_guard`) before pushing the new one — the dossier's `sections` entry confirms that lock covers `push_back`/`reap_finished_clients_locked`. `stop()` handles shutdown races by `shutdown(fd, SHUT_RDWR)` to unblock anyone stuck in a blocking read.

**2. `HealthMonitor::monitor_loop`** (`src/mcp/health_monitor.cpp:92`, spawned from `HealthMonitor::start`)
Polls watched server entries every 500ms. Safety: mutates the shared `watched_` map only inside `std::lock_guard<std::mutex> lock(watched_mutex_)` — confirmed as the lock held both by `monitor_loop` itself and, transitively, by `check_server` (its only callee, called while the lock is held). Sleeping between polls uses a *separate* `wake_mutex_`/`wake_cv_` (a `condition_variable::wait_for`) so the shutdown flag `running_` can be checked without holding `watched_mutex_` — i.e., it deliberately drops the data lock before waiting so a `stop()` call from another thread isn't blocked behind it.

**3. `StdioTransport::stderr_reader_loop`** (`src/mcp/transport_stdio.cpp:164`, spawned from `StdioTransport::open`)
Polls the child process's stderr fd and forwards lines to spdlog. Safety: this one has **no lock at all** in the dossier — it only reads a plain fd (`stderr_fd_`) and calls `logger->warn(...)` (spdlog's own internal locking covers the log sink), and loops on the `connected_` flag. It touches no other shared mutable state, so it's safe by not sharing anything, not by explicit synchronization.

**4. `SSETransport::sse_reader_loop`** (`src/mcp/transport_sse.cpp:107`, spawned from `SSETransport::open`)
Runs `httplib::Client::Get` with a streaming content-receiver callback that calls `process_sse_line` → `handle_sse_data` for each SSE line. Safety concern here: `process_sse_line` writes `current_event_type_` **with no lock held** (`writes`/`locks_held` both empty in the dossier). That's only safe if nothing else touches `current_event_type_` concurrently — the index can't confirm that from this side; I'd want to grep `handle_sse_data` and any main-thread readers of `current_event_type_` before calling this one clean. Flagging it as the weakest-looking link of the five.

## Summary of the safety pattern

Across the three genuinely-background loops (`accept_loop`, `monitor_loop`, `stderr_reader_loop`) the consistent idiom is: RAII `lock_guard`/`unique_lock` over a dedicated per-resource mutex (`client_threads_mutex_`, `watched_mutex_`), atomics for cross-thread flags (`finished`, `running_`, `connected_`) checked without a lock, and condition variables used for wakeup rather than busy-polling shared state. `sse_reader_loop`'s `current_event_type_` write is the one case where the index shows no lock and no atomic — that's a gap in the index's evidence, not a confirmed bug, but it doesn't fit the pattern the other three follow and is worth eyeballing directly in `transport_sse.h`/`.cpp`.
