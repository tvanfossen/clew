**Short answer:** Entropic runs work on background threads in about ten spawn sites. Most are long-lived service loops owned by a class that joins them in `stop()`/the destructor. The rest are short-lived pollers that are joined before the calling function returns. Safety comes from mutexes around shared state, `std::atomic` flags for stop and done signals, and joining before the owner goes away. The one exception is the detached async-ask thread, and one cross-thread `int` looks like a data race.

The index found 10 spawn sites, all `std::thread`/pthread. Two are test-only, so the production count is 8. Spawn detection only matches known primitives, so a custom spawn helper would not appear.

| Thread | Spawned in | Lifetime | What keeps it safe |
|---|---|---|---|
| `ExternalBridge::accept_loop` | `external_bridge.cpp:796` | Joined in `stop()` (l.833) | `running_` atomic; `poll(…, 500ms)` so it can notice shutdown; each accepted fd is checked with `SO_PEERCRED` (gh#34) before a thread is spawned |
| Per-client `serve_client` thread | `external_bridge.cpp:945` | Joined in `stop()` (l.850, 884) | `client_threads_mutex_` guards the vector; `stop()` does `shutdown(SHUT_RDWR)` to unblock reads; finished threads are reaped under the same mutex |
| `run_async_ask` worker | `external_bridge.cpp:1158` | **Detached** (l.1222) | `tasks_mutex_` guards `tasks_`; the sentinel is written under that lock so pollers see the same terminal state the notification reports |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | Joined (l.108) | `event_mutex_`, `watched_mutex_`, `wake_mutex_` |
| `StdioTransport::stderr_reader_loop` | `transport_stdio.cpp:164` | Joined (l.219) | `io_mutex_` |
| `SSETransport::sse_reader_loop` | `transport_sse.cpp:107` | Joined (l.139) | `pending_mutex_` |
| Cancel pollers (3 sites) | `inference_c_api.cpp:385`, `interface_factory.cpp:246`, `response_generator.cpp:413` | Joined in the dtor or before return | `std::atomic<bool>` done flags; the local state is captured by reference, which is safe only because the join happens first |

**Things to look at:**

1. **Detached async-ask thread.** `run_async_ask` captures `this` and is never joined. `stop()` joins the accept and client threads but not this one, so an in-flight ask could outlive the bridge. I did not confirm whether the destructor waits for running tasks, so treat this as an open question.

2. **Cross-thread plain `int` in the cancel path.** `ResponseGenerator::dispatch_batch_generate` has an observer thread write `cancel_int = 1` while the backend's `CancelFlagBridge` poller reads `*cancel_flag` (a plain `int*`, `inference_c_api.cpp:388`). That is an unsynchronized read/write pair, which is a data race under the C++ memory model. The code comment says the int is kept to avoid atomics across the `.so` boundary, but that does not make the race benign. The fix is a `std::atomic<int>` on the C side, or passing an atomic pointer internally.

3. **Lock ordering.** The index found three two-lock nestings, but none have resolved call sites, so I would not cite them as confirmed. The pairs are `event_mutex_ → adapter_mutex_` (`health_monitor.cpp:122`), `auth_mutex_ → key_mutex_` (`mcp_authorization.cpp:105`), and a test-only pair. None of them is taken in opposite orders, so no deadlock pair was found.

I did not run the tests or a sanitizer (TSan would confirm item 2 directly).