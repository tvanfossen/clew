Several parts of entropic run on their own threads, and most are guarded by per-handle locks, atomics, and join-on-destroy. I found two spots where the guard is missing or unverified.

**Threads spawned in the C++ code**

| Thread | Where | Lifetime | Safety mechanism |
|---|---|---|---|
| ExternalBridge accept loop | `src/facade/external_bridge.cpp:796` | Joined in `stop()` | `running_` atomic; `s_bound_sockets_mu` guards the socket registry |
| ExternalBridge per-client serve thread | `external_bridge.cpp:945` | Tracked in `client_threads_`, joined on stop, reaped when finished | `client_threads_mutex_` |
| Async `entropic.ask` worker | `external_bridge.cpp:1158` | **Detached** | `tasks_mutex_` guards task state and the sentinel write |
| HealthMonitor loop | `src/mcp/health_monitor.cpp:92` | Joined in `stop()` | `watched_mutex_`, `event_mutex_`, `wake_mutex_`/cv |
| SSE reader | `src/mcp/transport_sse.cpp:107` | Stopped in `close()` (join not checked) | `pending_mutex_`; `connected_`/`running_` atomics |
| Stdio stderr forwarder | `src/mcp/transport_stdio.cpp:164` | Not verified in this pass | `io_mutex_` on the write path (line 244) |
| Cancel pollers (3 sites) | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` | Per call; joined before the call returns | `done` flag set before join; RAII destructor joins |

**What keeps it safe**

- **Per-handle serialization.** `engine_handle.h:76` has an `api_mutex`, and the RAII guard at line 176 acquires it before the log scope. The header contract says "Serialized per-handle" (`entropic.h:94`, `:115`, `:144`).
- **Log routing across threads.** Each spawned thread opens a `HandleLogScope` with the owning handle's `log_id` (`external_bridge.cpp:797`, `:946`). The log routing is `thread_local` (`src/types/logging.cpp:36`), so without this, lines from a worker would go to the wrong session log.
- **Atomics for queries, mutexes for transitions.** `state_` is atomic and `transition_mutex_` covers only state changes (`architecture-cpp.md:458`, rule 10). `interrupt_flag_` in `engine.h:1415` is atomic.
- **Cancellation is cooperative.** The cancel flag is a `std::atomic<bool>` polled per token (rule 11).
- **MTP teardown.** `LlamaCppBackend::mtp_mutex_` is held across `generate_mtp` and across deactivate/unload teardown (`llama_cpp_backend.cpp:622`, `:746`, `:3915`). This prevents a use-after-free when the MTP head is torn down mid-decode.
- **Join discipline.** Pollers and monitor threads are joined in their destructors or `stop()`, and `ExternalBridge::stop()` documents an explicit shutdown order (`external_bridge.cpp:~620`).

**Gaps I found**

1. **Plain `int` cancel flag crosses threads.** `entropic_run_streaming` takes `int* cancel_flag` (`entropic.h:380`). In `response_generator.cpp:413`, an observer thread writes `cancel_int = 1` as a plain `int`, while the backend's poller reads `*cancel_flag` on another thread. This is a data race under the C++ memory model. It is benign on common hardware, but it is undefined behavior, and the ABI does not require atomics. Fix: use `_Atomic int` at the C boundary, or `std::atomic_ref<int>` internally.
2. **Detached async worker has no visible join.** The worker captures `this` and `handle_` and is detached (`external_bridge.cpp:1222`). I found no wait in `stop()` or `~ExternalBridge()`, and the only cancel path I saw is `context_clear` (`cancel_inflight_async_tasks`). If the handle is destroyed while a task is running, the worker could touch freed memory. I did not check whether `entropic_destroy` waits elsewhere, so this needs verifying.

Separately, two tool results ended with a note asking me to call a `dossier` tool. That tool isn't in my toolset and wasn't part of your question, so I ignored it.