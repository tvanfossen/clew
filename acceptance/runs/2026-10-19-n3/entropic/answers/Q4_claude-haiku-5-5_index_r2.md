Nine `std::thread` spawn sites in `src/` run off the caller's thread. The index's thread list reports only five, so I cross-checked with a grep. The safety comes from a few repeated patterns, and I found one spot where those patterns don't cover the lifetime.

**Threads and their guards**

| Thread | Spawned at | Lifetime and shutdown | Shared state / guard |
|---|---|---|---|
| `ExternalBridge` accept loop | `external_bridge.cpp:796` | Joined in `stop()` (`:832`). Polls with a 500 ms timeout and checks `running_`. | `running_` atomic. Rejects cross-uid peers via `SO_PEERCRED` before a thread is created. |
| Per-client serve thread | `external_bridge.cpp:945` | `stop()` calls `shutdown(SHUT_RDWR)` on each fd to wake blocked reads, then joins (`:846-851`). Finished threads are reaped on each accept. | `client_threads_mutex_` guards the vector. The log scope is propagated via `HandleLogScope`. |
| Async-ask worker (`run_async_ask`) | `external_bridge.cpp:1158`, **detached** (`:1222`) | **Not joined anywhere.** See the gap below. | `tasks_mutex_` guards the task map. The terminal status and sentinel are written under that lock. |
| `HealthMonitor::monitor_loop` | `health_monitor.cpp:92` | `stop()` sets `running_=false`, notifies the cv, and joins (`:102-109`). | `watched_mutex_` guards the watch list. `wake_mutex_` plus a cv gives a 500 ms sleep that stop can interrupt. Events go through `event_mutex_` and are swapped out, then delivered by `process_events()` on the engine thread, so the callbacks never run on the monitor thread. |
| `StdioTransport` stderr reader | `transport_stdio.cpp:164` | Joined at `:219`. | Not read in detail. |
| `SSETransport` reader | `transport_sse.cpp:107` | `close()` clears `running_`, calls `client_->stop()`, wakes `pending_cv_`, then joins (`:127-140`). | `pending_mutex_` and the `running_`/`connected_` atomics. |
| `CancelFlagBridge` poller | `inference_c_api.cpp:385` | Joined in the destructor. Polls every 10 ms. | `done_` and `cancel_` are atomics. Bridges an `int*` cancel flag across the C ABI into `std::atomic<bool>`. |
| `iface_generate_with_cancel` poller | `interface_factory.cpp:246` | Joined before return (`:262`). | `done` and `cancel_flag` are atomics. |
| `ResponseGenerator` observer | `response_generator.cpp:413` | Joined before return (`:429`). | `observer_done` is an atomic. |

The index's thread list finds only five of these (the accept, monitor, stdio and SSE threads, plus a test-only server). It misses the per-client, async-ask, cancel-poller and observer threads. Its list should not be treated as complete.

**What keeps it safe, in short**

1. **Lifecycle is explicit.** Most threads are joined in `stop()`, `close()` or the destructor. `entropic_destroy` stops the bridge first, before releasing the handle (`entropic.cpp:1884-1886`).
2. **Flags are atomics, and containers are behind mutexes.** The lock-use index lists 45 distinct lock identities. Client, task and watch containers each have their own mutex.
3. **Callbacks are marshalled.** Health events are queued and drained on the engine thread, so user callbacks don't run on the monitor thread.
4. **Blocked reads are woken, not abandoned.** `shutdown(SHUT_RDWR)` for sockets, `client_->stop()` for SSE, and short poll timeouts elsewhere.
5. **Lock ordering looks clean.** The nesting index shows three two-lock pairs with no reversed pair. All three are unverified (`resolved_sites=0`), so this is weak evidence.

**The gap: the detached async-ask thread**

`run_async_ask` captures `this` and `handle_`, runs `entropic_run` for as long as the task takes, then calls `broadcast_notification`. It is detached, and `ExternalBridge::stop()` does not wait for it. `entropic_destroy` calls `stop()` and then releases the handle. I found no in-flight counter or wait that would hold teardown until these tasks finish. If a task is still running when the handle is destroyed, the worker can touch a freed bridge or handle. I only checked the paths I read: `stop()`, the destructor, `entropic_destroy` and `handle_clear`. `handle_clear` cancels in-flight tasks, but teardown doesn't call that path.

I'd treat this as a probable use-after-free on destroy-while-async-running, not a confirmed one. A test that destroys a handle with an async ask in flight, under TSan or ASan, would settle it. The fix is to track in-flight workers and join them in `stop()`, or to switch to a joinable thread that `stop()` owns.