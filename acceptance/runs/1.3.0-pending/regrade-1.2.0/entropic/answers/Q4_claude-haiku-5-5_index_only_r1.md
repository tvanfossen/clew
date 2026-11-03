Nine thread spawn sites in production code run off the caller's thread, plus one in a test mock. The index gives two kinds of safety evidence: mutexes and atomics guard shared state, and a per-handle socket registry stops two bridges from binding the same path. It does not show how every thread is joined or torn down, so that part is unverified.

**Spawn sites in production code (from `search` threads and `dossier`)**

| Thread | Spawned in | What it does |
|---|---|---|
| Async ask worker (`<lambda>@1158`) | `ExternalBridge::run_async_ask` | Runs `entropic_run` detached for `entropic.ask`, then updates task state and sends a progress notification. |
| Accept loop | `ExternalBridge::start` | Polls the listen socket every 500 ms, checks peer uid, and spawns one serve thread per client. |
| Per-client serve (`ct->thread`) | `ExternalBridge::accept_loop` | Serves one MCP client until disconnect. |
| Health monitor | `HealthMonitor::start` | Runs `monitor_loop`. |
| Stdio stderr reader | `StdioTransport::open` | Drains the child process's stderr. |
| SSE reader | `SSETransport::open` | Reads the SSE stream. |
| Cancel poller (`CancelFlagBridge`) | `inference_c_api.cpp:385` | Mirrors an `int` cancel flag into an atomic for the backend. |
| Cancel poller (`poller`) | `iface_generate_with_cancel` | Same bridge for the orchestrator batch path. |
| Interrupt observer | `ResponseGenerator::dispatch_batch_generate` | Copies the engine's `interrupt_flag_` into the C-ABI cancel int during a batch call. Joined before return. |

The eighth thread, `listen_after_bind` in `MockSSEServer`, lives in a test. The index reports 10 spawn sites in total, all first-party, and no vendored ones.

**What keeps it safe**

- **Shared state is behind named mutexes.** The async-ask worker takes `ExternalBridge::tasks_mutex_` for each task-map write. It also writes the sentinel file under that lock, so an external monitor that sees the sentinel can call `entropic.ask_status` and get the same terminal state. The accept loop takes `client_threads_mutex_` before pushing and reaping client threads. `HealthMonitor` uses `event_mutex_`, `watched_mutex_` and `wake_mutex_`. The SSE and stdio transports have `pending_mutex_` and `io_mutex_`. I did not confirm which data each of these guards inside the reader loops.
- **Lifecycle flags are atomics.** `running_` and `finished` are atomics, and the poller threads poll `std::atomic<bool>` done flags with release/acquire ordering. The cancel bridges use a 10 ms poll rather than a shared mutex.
- **Threads are scoped and joined where it matters.** The per-call observer and poller threads are joined before the function returns. Each spawned thread also installs a `HandleLogScope` so its logs reach the owning handle's session log.
- **Socket ownership is claimed up front.** `ExternalBridge::start` records the canonical socket path in a process-wide set under `s_bound_sockets_mu` before unlinking and binding. A second handle in the same process that targets the same path is refused.
- **Per-client cleanup.** Each serve thread closes its own fd, sets `finished`, and the accept loop joins and erases finished threads. `stop()` shuts down the fd to wake blocking reads.
- **Peer authentication at accept.** `peer_uid_matches` (SO_PEERCRED) closes connections from other uids before any serve thread is created.

**Lock ordering.** The index records three two-lock nestings, and none appears in both orders, so it shows no inversion. However, none of the three has a resolved receiver, so I would not call them confirmed:
- `event_mutex_` → `adapter_mutex_` in `HealthMonitor::process_events`
- `auth_mutex_` → `key_mutex_` in `check_access`
- `MockSSEServer::mu_` → `adapter_mutex_` in a test

**What I could not verify from the index**

- **Lifetime of the detached async-ask thread.** It captures `this`, and the body I read shows no join. Nothing in the index proves the bridge outlives it. The shutdown path that waits for in-flight asks is not visible to me.
- **Accept thread teardown.** I did not read `ExternalBridge::stop()`, so I cannot confirm that `accept_thread_` is joined there.
- **Reader-loop locking.** I did not read the `StdioTransport` and `SSETransport` reader bodies, so their use of `io_mutex_` and `pending_mutex_` is inferred from the lock names.
- **`HealthMonitor::monitor_loop` body.** Only its spawn site was read.