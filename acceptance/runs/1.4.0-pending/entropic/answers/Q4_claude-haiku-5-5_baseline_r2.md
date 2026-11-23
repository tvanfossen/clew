Several parts of entropic run on their own threads. Most are joined before their owner returns, and the one place that is not is a real gap.

**Threads and what keeps each safe**

| Thread | Where | Lifetime | Safety mechanism |
|---|---|---|---|
| External bridge accept loop | `src/facade/external_bridge.cpp:796` | Joined in `stop()` | `running_` is atomic; `poll()` with a 500 ms timeout lets it notice shutdown |
| Per-client serve threads | `external_bridge.cpp:945` | Owned by `client_threads_`, joined in `stop()` | `client_threads_mutex_`; `stop()` drains the list, then `shutdown(SHUT_RDWR)` wakes blocked reads before join |
| Async `entropic.ask` worker | `external_bridge.cpp:1158`, `.detach()` at `:1222` | **Detached, never joined** | `tasks_mutex_` guards the registry and the sentinel write; `HandleLogScope` tags logs |
| Inference cancel poller | `interface_factory.cpp:246`, `inference_c_api.cpp:385` | Joined before return | Atomic `done` flag; captures are by pointer to the caller's frame, which outlives the join |
| Response-generator observer | `response_generator.cpp:413` | Joined before return | Atomic `observer_done`; RAII `CancelFlagBridge` in `inference_c_api.cpp:419` |
| Health monitor | `src/mcp/health_monitor.cpp:93` | Joined in `stop()` | `watched_mutex_` for the watch table, `event_mutex_` for the queue; callbacks are drained by `process_events()` on the engine thread, so user callbacks never run on the monitor thread |
| MCP stdio stderr reader | `transport_stdio.cpp:164` | Joined on close | Its own fd, closed after the join |
| MCP SSE reader | `transport_sse.cpp:107` | Joined on disconnect | `pending_mutex_`; `client_->stop()` runs first to unblock the reader |
| Backend transitions and MTP | `llama_cpp_backend.cpp:622,746,3915` | Caller threads | `transition_mutex_` guards state transitions only; `state_` is atomic; `mtp_mutex_` serialises MTP decode against teardown |

The documented rules behind this are in `docs/architecture-cpp.md`: decision #10 (atomic state queries, mutex only for transitions) and decision #11 (cancel via an atomic flag). Thread-local `HandleLogScope` (`src/types/logging.cpp:36`) routes each thread's logs to the right handle.

**The weak spot: the detached async-ask worker**

`run_async_ask` captures `this` (the `ExternalBridge`) and the raw `handle_`, then detaches. `stop()` (`external_bridge.cpp:~826`) joins the accept thread and client threads, but it does not wait for async workers. The destructor just calls `stop()`. `handle_` is also reset in `entropic.cpp:1537` and `:1885-1886`.

The mitigation is best-effort: `cancel_inflight_async_tasks` (`:434`) raises the interrupt and polls for about 1 s (20 × 50 ms). If a worker is still inside `entropic_run` after that, its later calls to `update_task_phase`, `write_sentinel` and `broadcast_notification` touch a bridge that may already be destroyed. That is a use-after-free risk. I did not confirm whether handle teardown ever waits on that worker, so this is a risk to verify, not a proven bug. A fix would track in-flight workers with a counter and join them in `stop()`.

**Smaller issue**

`accept_loop` reads the plain `int listen_fd_` (`:920, :926`) while `stop()` writes it (`:~830`). `running_` is ordered first, but the field is not atomic, so this is a data race in the strict C++ sense. It is probably benign in practice because `accept()` on a closed fd just returns an error, but it should be an atomic or taken under a lock.

I did not run tests or a thread sanitiser. These findings come from reading the code.

A `PostToolUse` hook output suggested a `dossier` lookup tool. I have no such tool, so I ignored it and used `Grep`, `Read` and `Bash`.