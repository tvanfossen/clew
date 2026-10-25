The index shows five thread spawn sites in entropic's own code, four of them in production. Each one is guarded by a mutex or an atomic flag, and the shutdown path joins or closes what it started. The index doesn't fully settle the stdio and SSE transports, so I've marked those below.

**Threads other than the caller's** (spawn sites from `search corpus=threads`)

| Thread | Spawned in | What it does |
|---|---|---|
| `ExternalBridge::accept_loop` | `ExternalBridge::start` (`src/facade/external_bridge.cpp:796`) | Polls the listen socket, accepts MCP clients, and starts one serve thread per client |
| per-client serve thread | inside `accept_loop` | Runs `serve_client` for one connection |
| `HealthMonitor::monitor_loop` | `HealthMonitor::start` (`src/mcp/health_monitor.cpp:92`) | Checks watched MCP servers every 500 ms |
| `StdioTransport::stderr_reader_loop` | `StdioTransport::open` (`src/mcp/transport_stdio.cpp:164`) | Forwards child-process stderr to the log |
| `SSETransport::sse_reader_loop` | `SSETransport::open` (`src/mcp/transport_sse.cpp:107`) | Reads the SSE event stream |

The fifth spawn site, `listen_after_bind`, is in `tests/unit/mcp/transport_sse_test.cpp` and is test scaffolding.

**What keeps it safe**

1. **Shared state sits behind named mutexes.** The index lists 45 lock identities in the first-party code. The ones on these paths are:
   - `ExternalBridge`: `client_threads_mutex_` guards the client list, `tasks_mutex_` and `subscribers_mutex_` guard task and subscriber state, and `s_bound_sockets_mu` guards a process-wide set of socket paths.
   - `HealthMonitor`: `watched_mutex_` guards the watch map, `event_mutex_` guards the event queue, and `wake_mutex_` with a condition variable provides an interruptible sleep.
   - `StdioTransport`: `io_mutex_`.
   - `MCPAuthorizationManager`: `auth_mutex_`, held across `check_access`.

2. **Callbacks are not run on the background thread.** `HealthMonitor::process_events` (documented as "call on engine thread") swaps the event queue out under `event_mutex_`, releases the lock, and then invokes the status callback. The callback therefore runs on the engine thread, not while the lock is held.

3. **Lifecycle flags are atomic.** `ExternalBridge` uses `running_` (`store`/`load`), and `SSETransport` uses `running_` and `connected_` (`load`). The index does not show their declared types, so this is the usage pattern I can see, not a verified declaration.

4. **Shutdown is ordered and joins everything.** `ExternalBridge::stop` does the following, in order:
   - Sets `running_` to false.
   - Closes the listen fd and joins the accept thread, so no new clients can spawn after the join.
   - Moves the client list out under its mutex.
   - Calls `shutdown(SHUT_RDWR)` on each client fd to wake blocked reads.
   - Joins each client thread.
   - Removes the socket file and releases the path claim.

5. **Thread-local log routing.** Each thread body installs a `HandleLogScope`, so its log lines go to the owning handle's session log (gh#59).

6. **Access control and peer checks on the accept path.** Each accepted fd is checked with `peer_uid_matches` (SO_PEERCRED) before a serve thread is created (gh#34). `check_access` runs under `auth_mutex_`.

**Caveats**

- The lock-nesting data has three ordered pairs, and none shows the same two locks taken in opposite orders. That is the deadlock pattern the index would flag, so none is reported. The index makes no deadlock claim itself.
- One pair, `event_mutex_` → `adapter_mutex_` via `process_events`, has zero resolved sites. The `swap` inside it is marked `receiver_unverified`, so I wouldn't rely on that pair.
- I did not dossier `StdioTransport::open` as a qualified name, so I haven't verified its join or teardown path. The SSE `open` path is confirmed. Its reader thread is not joined in `open` itself. The index's `close()` callee is the place to check that.