Several parts of entropic run off the caller's thread. The index's thread layer finds five spawn sites, but a grep for `std::thread` found more it misses. Safety comes from a few repeated patterns: handing work to the engine thread through a queue, guarding shared state with mutexes or atomics, and joining threads on shutdown. I found two real gaps and one likely data race.

**Background threads**

| Thread | Spawn site | What it does | Joined by |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` | Polls the listen socket (500 ms) and gates each fd on `SO_PEERCRED` before spawning a client thread | `ExternalBridge::stop()` (`:826`) |
| Per-client `serve_client` threads | `external_bridge.cpp:945` (lambda, not indexed) | Serves one MCP client each | `stop()` and `reap_finished_clients_locked()` |
| Detached async-ask worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` (lambda, not indexed) | Runs `entropic_run` for `entropic.ask` with `async`, then writes the task registry and sentinel | **Nothing** (see gap 1) |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Checks server health and reconnects every 500 ms | `HealthMonitor::stop()` |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Forwards child stderr to the log | `StdioTransport::close()` |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Reads the SSE event stream | `SSETransport::close()` |
| Cancel pollers | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` (lambdas, not indexed) | Turn an `int*` cancel flag into an atomic for the backend | Joined in the same scope or the destructor |

`MockSSEServer::listen_after_bind` is test-only.

**What keeps it safe**

- **Hand-off to the engine thread.** `HealthMonitor::process_events()` (`health_monitor.cpp:118`) swaps the event queue under `event_mutex_` and calls the status callback on the engine thread. The monitor thread only posts events, so user callbacks never run on it.
- **Mutexes around shared state.** `watched_mutex_` covers each health pass. `client_threads_mutex_` guards the client vector. `tasks_mutex_` guards the async task map, and the sentinel is written under it, so external watchers see the same state the registry holds. `io_mutex_` serialises stdio request and response I/O.
- **Atomics for flags.** `running_` (`health_monitor.h:137`, `transport_sse.h:92`, `external_bridge.h:386`), `connected_`, and `cancel_flag_` are `std::atomic<bool>`, so the threads can read them without locks.
- **Ordered shutdown.** `ExternalBridge::stop()` clears `running_`, closes the listen socket, joins the accept thread, `shutdown(SHUT_RDWR)`s each client fd to wake blocked reads, then joins the client threads. Health and SSE shutdown set the flag, notify or stop the client, and join.
- **Bounded blocking.** Socket and pipe waits use short poll slices (500 ms, or 100 ms for `read_line`) so the threads notice shutdown and cancel promptly.
- **Log routing.** `HandleLogScope` is copied into each spawned thread, so their logs go to the owning handle's session.

**Gaps and risks**

1. **Detached async worker outlives its owner.** The lambda at `external_bridge.cpp:1158` captures `this` and uses `handle_`, and `stop()` never waits for it. If the bridge or handle is destroyed while an async ask is still running, the worker touches freed state. I did not check whether the destructor or handle teardown waits for `tasks_`. Treat this as a likely use-after-free until someone confirms it.
2. **Stdio stderr close race.** `StdioTransport::close()` (`transport_stdio.cpp:210`) sets `connected_ = false`, then closes `stderr_fd_` and sets it to -1 before joining the reader. The reader reads `stderr_fd_` without synchronisation, and `stderr_fd_` is a plain `int`. Join the thread before closing the fd, or make the fd atomic.
3. **Plain `int*` cancel flag.** `response_generator.cpp:405–416` writes `cancel_int`, a plain `int`, from the observer thread while the calling thread's backend reads it. That is a data race under the C++ memory model, even if it is benign on current hardware. The fix is an atomic, which the C ABI forbids; the other pollers avoid this by bridging through an internal atomic.

The thread index undercounts: it finds spawn sites only where a named entry function resolves, so lambda spawns such as gaps 1 and 3 do not appear. The lock layer also has three nested lock pairs with no resolved call sites, so none of them is confirmed as a deadlock risk.