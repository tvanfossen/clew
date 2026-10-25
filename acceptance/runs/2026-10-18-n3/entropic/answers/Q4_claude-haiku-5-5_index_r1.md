Five background threads are visible in the index, but a grep of `src/` finds nine `std::thread` spawn sites. The index misses the per-client serve thread, the detached async-ask worker, and three short-lived inference pollers. Safety rests on three patterns: atomics for flags, one mutex per shared container, and joins on every shutdown path. A few spots fall short of that.

**Long-lived threads**

| Thread | Spawn site | What it touches | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` | `listen_fd_`, `client_threads_` | `running_` is atomic. `poll` has a 500 ms timeout so it can see shutdown. Clients are checked with `SO_PEERCRED` before a thread is spawned. |
| Per-client `serve_client` | `external_bridge.cpp:945` | its own fd, the bridge's task registry | The vector `client_threads_` is guarded by `client_threads_mutex_`. Each thread sets an atomic `finished` flag, and `reap_finished_clients_locked()` joins and erases finished entries. |
| Async-ask worker | `external_bridge.cpp:1158` | `tasks_` | `tasks_mutex_` guards every access, and the sentinel file is written under that lock. This thread is detached (`.detach()` at line 1222). |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | `watched_` | `watched_mutex_` covers each check pass. `wake_cv_` with `wake_mutex_` gives a prompt wake on stop. |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | child stderr fd | `connected_` is atomic. Joined in close (line 219). |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | HTTP stream callbacks | `connected_` and `running_` are atomic. Joined at line 139. |

Health events are queued under `event_mutex_` by the monitor thread. `process_events()` swaps the queue out under the lock and runs the callbacks after releasing it, on the engine thread. Callbacks never run on the monitor thread and never run under a lock.

**Short-lived helper threads**

- `response_generator.cpp:413` starts an observer that polls the interrupt flag and writes `cancel_int`. It is joined at line 429. If `generate_cancellable` throws, the joinable `std::thread` is destroyed unjoined and the process terminates. An RAII guard would fix that.
- `inference_c_api.cpp:385` (`CancelFlagBridge`) and `interface_factory.cpp:246` are poller threads. Each is joined on its destructor or return path.

**Gaps I found while reading**

1. **Detached async worker outlives the bridge.** The lambda captures `this`, and `stop()` and the destructor (line 612) never wait for it. Only `context_clear` cancels in-flight tasks, so destroying the handle while a task runs looks like a use-after-free. I did not confirm this at runtime.
2. **Unsynchronised `int` shared across threads.** The observer at `response_generator.cpp:416` writes a plain `int` that `CancelFlagBridge` reads concurrently. That is a formal data race even though the loop is benign in practice. The same pattern applies to `ct->fd` in `stop()` and `listen_fd_`, which are plain ints read while the owning thread writes them.
3. **Lock nesting is unverified.** The index reports three two-lock pairs, and all three have `resolved_sites=0`, so none of them is confirmed. In the code I read there is no reversed pair.

Overall, the design rules are consistent: atomics for state flags, one mutex per container, callbacks invoked outside locks, and joins on shutdown. The real holes are the detached task worker and the unsynchronised `int` flags in the inference cancel path.