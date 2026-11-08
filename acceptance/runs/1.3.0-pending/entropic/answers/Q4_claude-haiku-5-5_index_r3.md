Ten thread spawn sites in first-party code, and the safety comes from a few patterns rather than one global lock. Nine of them are in `src/`; the tenth is a test helper. A grep for `std::thread`, `std::async` and `pthread_create` agrees with the index.

**Background threads**

| Thread | Spawn site | What it does | Shared state it touches |
|---|---|---|---|
| Bridge accept loop | `external_bridge.cpp:796` | `poll` + `accept` with a 500 ms timeout, checks peer uid, spawns a client thread | `running_` (atomic), `client_threads_mutex_` |
| Per-client serve threads | `external_bridge.cpp:945` | Serves one MCP client, then closes its fd and sets `finished` | `client_threads_mutex_`, `subscribers_mutex_` |
| Async-ask worker | `external_bridge.cpp:1158`, `.detach()` at 1222 | Runs `entropic_run` for `entropic.ask`, writes the sentinel, broadcasts progress | `tasks_mutex_`, `subscribers_mutex_` |
| Health monitor | `health_monitor.cpp:92` | Checks servers every 500 ms | `watched_mutex_`, `wake_mutex_`, `event_mutex_` |
| Stdio stderr reader | `transport_stdio.cpp:164` | Drains child stderr | not checked |
| SSE reader | `transport_sse.cpp:107` | Reads the SSE stream | `pending_mutex_` (per the lock list; not checked against the loop) |
| Cancel poller (C API) | `inference_c_api.cpp:385` | Polls an `int*` cancel flag, sets an atomic | atomics only |
| Cancel poller (batch) | `interface_factory.cpp:246` | Same pattern, for `iface_generate_with_cancel` | atomics only |
| Interrupt observer | `response_generator.cpp:413` | Mirrors the engine's interrupt flag into an `int` for the duration of one batch call | atomics only |

**What keeps them safe**

1. **Hand-off by queue, not by callback.** The health monitor never runs user code on its own thread. `monitor_loop` pushes events onto `event_queue_`, and `process_events()` swaps the queue out under `event_mutex_` and invokes the callbacks on the engine thread after releasing the lock (`health_monitor.cpp:118`).

2. **Cancellation through atomics and a join.** The pollers and observers read a flag every 10 ms and set an atomic. `iface_generate_with_cancel` and `dispatch_batch_generate` set `done`/`observer_done` and join the poller before returning, so the captured-by-reference locals stay alive. The C ABI only ever sees `int*`, so no `std::atomic` crosses the `.so` boundary.

3. **Mutex-guarded registries with a fixed ordering.** Task state lives under `tasks_mutex_`, and the sentinel is written inside that lock before the progress notification goes out (`external_bridge.cpp:1172-1183`). The accept loop reaps finished clients under `client_threads_mutex_`.

4. **Broadcast without holding the lock while writing.** `broadcast_notification` snapshots the subscriber set under `subscribers_mutex_`, sends with `MSG_DONTWAIT | MSG_NOSIGNAL`, and drops any fd that fails or only partly writes. Dead fds are removed under the lock in a second pass (`external_bridge.cpp:1285-1317`). A slow client cannot block the async worker, which was the deadlock that issue #4 fixed.

5. **Process-wide socket claim.** `start()` inserts the canonical socket path into `s_bound_sockets` under `s_bound_sockets_mu` before unlinking or binding, so two in-process bridges cannot race on one path (`external_bridge.cpp:756-804`). Each accepted fd is checked with `SO_PEERCRED` before a serve thread is created.

6. **Per-thread log routing.** Every bridge thread installs a `HandleLogScope` with the owning handle's `log_id`, so log lines go to the right session even on background threads.

**Lock-order evidence**

The index lists 45 lock identities and three nested pairs: `event_mutex_`→`adapter_mutex_`, `auth_mutex_`→`key_mutex_`, and a test mutex→`adapter_mutex_`. None of the pairs appears in the opposite order, so no inversion is recorded. However, all three pairs have `resolved_sites=0`, meaning the receiver of the nested call was never verified. Treat "no deadlock" as unconfirmed.

**Risks I found but did not fully verify**

- **The async-ask worker outlives its owner.** The worker is detached (`external_bridge.cpp:1222`) and captures `this`. `~ExternalBridge` calls `stop()`, and I did not confirm that `stop()` waits for in-flight workers. The only wait I found is the best-effort ~1 s poll in `cancel_inflight_async_tasks` (`external_bridge.cpp:434-443`), which the doc comment says can return with workers still running. If the bridge is destroyed while `entropic_run` is active, the worker dereferences a dead `this`. This is the most important thing to check.
- **`monitor_loop` reads `running_` without an explicit `.load()`** (`health_monitor.cpp:139`). Whether that is safe depends on `running_` being `std::atomic<bool>`; I did not check the declaration.
- **The index can miss spawn primitives.** Its thread list only covers patterns it knows about. The grep confirms that no other primitive appears in `src/`, but a project-specific wrapper would not show up.