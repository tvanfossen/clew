The off-caller threads in entropic are a small set of spawn sites, all in the first-party code. Safety rests mostly on a mutex per shared structure, atomics for flags, and explicit join/shutdown on teardown. Two spots look unsafe as written, and I did not confirm either by running anything.

**Threads that run off the caller's thread** (index reports 10 spawn sites, all first-party, 0 external)

| Thread | Spawn site | What it does |
|---|---|---|
| ExternalBridge accept loop | `external_bridge.cpp:796` | `poll()` with 500 ms timeout, accepts clients |
| Per-client serve thread | `external_bridge.cpp:945` | One per accepted MCP client |
| Async `entropic.ask` worker | `external_bridge.cpp:1158` (detached at `:1222`) | Runs `entropic_run` for a task |
| HealthMonitor loop | `health_monitor.cpp:92` | Polls MCP server health |
| SSE reader / stdio stderr reader | `transport_sse.cpp:107`, `transport_stdio.cpp:164` | Reads transport streams |
| Batch-generate observer | `response_generator.cpp:413` | Mirrors the engine interrupt flag into a C int |
| Cancel pollers | `interface_factory.cpp:246`, `inference_c_api.cpp:385` | Bridge the C int cancel flag to the backend |

**What keeps it safe**

- **Per-structure mutexes, short critical sections.** `tasks_mutex_`, `subscribers_mutex_`, and `client_threads_mutex_` in ExternalBridge; `event_mutex_` in HealthMonitor; plus about 45 lock identities repo-wide.
- **Snapshot, then act outside the lock.** `broadcast_notification` (`external_bridge.cpp:1290`) copies the subscriber set under the lock, sends without it, then re-locks only to drop dead fds.
- **Swap-and-drain for events.** `HealthMonitor::process_events` swaps the queue out under lock and invokes callbacks on the engine thread, not the monitor thread.
- **Non-blocking writes.** Broadcast uses `MSG_DONTWAIT | MSG_NOSIGNAL`, so one stalled client cannot wedge the async worker. The cost is that slow subscribers are dropped.
- **Ordering for terminal state.** The completion sentinel is written under `tasks_mutex_` before the progress notification, so a poller sees the same state the notification announces.
- **Atomics for flags.** `interrupt_flag_` uses `exchange`, `pause_flag_` and `running_` are atomic, and the poller loops use `done` flags with acquire/release.
- **Teardown.** `ExternalBridge::stop()` (`external_bridge.cpp:826`) closes the listen fd, joins the accept thread, `shutdown(SHUT_RDWR)`s each client to unblock reads, then joins them. Each client thread's `finished` flag lets `reap_finished_clients_locked` join and erase on the accept loop.
- **Security gate.** `SO_PEERCRED` uid check (`peer_uid_matches`) runs before a serve thread is spawned.
- **Log routing.** `HandleLogScope` is propagated into each spawned thread so logs land in the owning handle's session log.

**Where I'd look harder**

1. **Detached async worker outlives its owner.** The worker at `external_bridge.cpp:1158` captures `this` and runs `.detach()` at `:1222`. Nothing I read joins it. `cancel_inflight_async_tasks` only polls about 1 s, and its own doc says detached workers "may still be in flight when this returns." If the handle is destroyed while a task runs, the worker could touch a freed bridge. I did not trace `entropic_destroy` to confirm whether it waits for in-flight tasks.
2. **Plain-int cancel flag.** In `dispatch_batch_generate` (`response_generator.cpp:413`), the observer thread writes a non-atomic `int cancel_int` that the backend poller reads through `int*`. That is a data race under the C++ memory model, and the same `int*` pattern appears in `iface_generate_with_cancel` and `CancelFlagBridge`. It may be benign on the platforms in use, but it is not guaranteed. The fix is `std::atomic<int>` or an atomic-backed bridge, which means checking whether the C ABI contract allows it.
3. **Lock-order data is thin.** The index reports 3 two-lock nestings, and every one has `resolved_sites=0`, so none is confirmed. It found no opposite-order pair, so it shows no deadlock risk. I did not read the stdio/SSE/HealthMonitor loop bodies, so I can't speak to their internal locking.