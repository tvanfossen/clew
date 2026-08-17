# Q1 — src — sonnet — run 1

## Mutex enumeration — entropic (first-party `src/`/`include/`, excluding `extern/llama.cpp` vendor tree and `tests/`)

I grepped `src/` and `include/` for `std::mutex`, `std::shared_mutex`, `std::recursive_mutex`, `std::timed_mutex` declarations (member fields and file-scope statics), separately from their lock-site usages, and cross-checked names against every `lock_guard`/`unique_lock`/`shared_lock` call site. No `pthread_mutex_t`, `std::atomic_flag` spinlocks, or other hand-rolled lock primitives exist in first-party code (`grep` for those returned nothing).

**41 distinct declared mutex objects/fields:**

| # | Name | Type | Location |
|---|---|---|---|
| 1 | `io_mutex_` | mutex | `include/entropic/mcp/transport_stdio.h:158` |
| 2 | `auth_mutex_` | mutex | `include/entropic/mcp/mcp_authorization.h:148` |
| 3 | `tasks_mutex_` | mutex | `include/entropic/mcp/external_bridge.h:225` |
| 4 | `client_threads_mutex_` | mutex | `include/entropic/mcp/external_bridge.h:403` |
| 5 | `subscribers_mutex_` | mutex | `include/entropic/mcp/external_bridge.h:414` |
| 6 | `tools_mutex_` | mutex | `include/entropic/mcp/external_client.h:121` |
| 7 | `pending_mutex_` (SSE) | mutex | `include/entropic/mcp/transport_sse.h:95` |
| 8 | `mutex_` (Database) | mutex | `include/entropic/storage/database.h:147` |
| 9 | `key_mutex_` | mutex | `include/entropic/mcp/mcp_key_set.h:126` |
| 10 | `write_mutex_` (PermissionPersister) | mutex | `include/entropic/storage/permission_persister.h:56` |
| 11 | `mutex_` (PromptCache) | mutex | `src/inference/prompt_cache.h:194` |
| 12 | `mutex_` (ToolCallHistory) | **shared_mutex** | `include/entropic/mcp/tool_call_history.h:113` |
| 13 | `write_mutex_` (AuditLogger) | mutex | `include/entropic/storage/audit_logger.h:144` |
| 14 | `s_ggml_log_mu` (file-static) | mutex | `src/inference/inference_c_api.cpp:615` |
| 15 | `watched_mutex_` | mutex | `include/entropic/mcp/health_monitor.h:131` |
| 16 | `event_mutex_` | mutex | `include/entropic/mcp/health_monitor.h:134` |
| 17 | `wake_mutex_` | mutex | `include/entropic/mcp/health_monitor.h:139` |
| 18 | `mu_` (Logger) | mutex | `src/types/logging.cpp:113` |
| 19 | `s_session_paths_mu` (file-static) | mutex | `src/types/logging.cpp:132` |
| 20 | `mtp_mutex_` | mutex | `src/inference/llama_cpp_backend.h:647` |
| 21 | `seq_id_mutex_` | mutex | `src/inference/llama_cpp_backend.h:1053` |
| 22 | `mutex_` (ThroughputTracker) | mutex | `include/entropic/inference/throughput_tracker.h:106` |
| 23 | `registry_mutex_` (GrammarRegistry) | mutex | `include/entropic/inference/grammar_registry.h:170` |
| 24 | `mutexes_` (HookRegistry) | **`std::array<shared_mutex, ENTROPIC_HOOK_COUNT_>`** — 23 instances | `include/entropic/core/hook_registry.h:154`, size from `include/entropic/types/hooks.h:36-89` |
| 25 | `swap_mutex_` (Orchestrator) | mutex | `include/entropic/inference/orchestrator.h:559` |
| 26 | `api_mutex` (EngineHandle) | mutex | `src/facade/engine_handle.h:76` |
| 27 | `mutex_` (ProfileRegistry) | mutex | `include/entropic/inference/profile_registry.h:109` |
| 28 | `s_bound_sockets_mu` (file-static) | mutex | `src/facade/external_bridge.cpp:50` |
| 29 | `transition_mutex_` (Backend) | mutex | `include/entropic/inference/backend.h:756` |
| 30 | `eval_mutex_` (Backend) | mutex | `include/entropic/inference/backend.h:757` |
| 31 | `mutex_` (CompactorRegistry) | **shared_mutex** | `include/entropic/core/compactor_registry.h:194` |
| 32 | `delegation_cb_mutex_` (Engine) | mutex | `include/entropic/core/engine.h:1425` |
| 33 | `queue_mutex_` (Engine) | mutex | `include/entropic/core/engine.h:1444` |
| 34 | `overrides_mutex_` (ConstitutionalValidator) | mutex | `include/entropic/core/constitutional_validator.h:561` |
| 35 | `result_mutex_` | mutex | `include/entropic/core/constitutional_validator.h:588` |
| 36 | `pending_mutex_` (ConstitutionalValidator) | mutex | `include/entropic/core/constitutional_validator.h:610` |
| 37 | `attempt_boundary_mutex_` | mutex | `include/entropic/core/constitutional_validator.h:627` |
| 38 | `critique_cbs_mutex_` | mutex | `include/entropic/core/constitutional_validator.h:644` |
| 39 | `slots_mutex_` (SecondaryModelLoader) | mutex | `include/entropic/inference/secondary_model_loader.h:151` |
| 40 | `identities_mutex_` (IdentityManager) | **shared_mutex** | `include/entropic/core/identity_manager.h:317` |
| 41 | `adapter_mutex_` (AdapterManager) | mutex | `include/entropic/inference/adapter_manager.h:212` |

## Heavily-used mutex: `adapter_mutex_` (`AdapterManager`)

This is the single mutex with the most lock sites in one file — 11 `std::lock_guard<std::mutex> lock(adapter_mutex_)` sites in `src/inference/adapter_manager.cpp` (lines 79, 126, 165, 209, 242, 295, 344, 371, 387, 402, 418).

The most consequential critical section is `AdapterManager::swap()` (`src/inference/adapter_manager.cpp:236-273`), locked at line 242. While `adapter_mutex_` is held, the following executes:

1. A `std::unordered_map` lookup/validity check (`adapters_.find(name)`, `src/inference/adapter_manager.cpp:246-249`).
2. `fire_swap_hook(active_name_, name, it->second.path)` (`src/inference/adapter_manager.cpp:250`, implementation at `:466-490`), which:
   - Builds a `nlohmann::json` context object and serializes it (`:478-480`).
   - Calls `hooks_.fire_pre(hooks_.registry, ENTROPIC_HOOK_ON_ADAPTER_SWAP, ctx_str.c_str(), &modified)` (`:483-487`) — this dispatches into `HookRegistry::fire_pre` (`src/core/hook_registry.cpp:126-169`), which itself briefly takes a `shared_lock` on one of the 23 `mutexes_` array slots inside `snapshot()` (`hook_registry.cpp:113`) to copy the callback vector, releases it, then **synchronously invokes every registered pre-hook callback** for that hook point in a `try/catch` (`hook_registry.cpp:139-152`) — arbitrary user code runs here, all while `adapter_mutex_` is still held by the outer `swap()` call.
3. Map mutation to mark the previous HOT adapter `WARM` (`:256-261`).
4. `apply_adapter(ctx, target.handle, target.scale)` (`:268`), which calls straight into `llama_set_adapters_lora()` (`src/inference/adapter_manager.cpp:38-42`) — a call into the vendored llama.cpp inference backend.
5. State/bookkeeping updates (`active_name_ = name`, `:271`).
6. A `logger->info(...)` call formatting and emitting a log line (`:273-274`).

So `adapter_mutex_` is held across: a hook dispatch that runs arbitrary registered callback code, a call into the llama.cpp C API, and a logging call — not just the map mutation the mutex's own comment (`///< Guards transitions and map`, `include/entropic/inference/adapter_manager.h:212`) suggests. The same pattern (map lookup + `apply_adapter`/`llama_set_adapters_lora` + logging, all under this one mutex) repeats in `load()` (`:72-107`, additionally calling the heavyweight `llama_adapter_lora_init()` at `:88`), `unload()` (`:126-147`), `activate()` (`:151-190`), and `deactivate()` (`:196-220`).

## Distinct mutex count and confidence

- **41 distinct declared mutex fields/statics**, of which 38 are `std::mutex` and 3 are `std::shared_mutex` (`identities_mutex_`, `tool_call_history`'s `mutex_`, `compactor_registry`'s `mutex_`).
- One of those 41 declarations (`HookRegistry::mutexes_`) is an array of 23 `std::shared_mutex` instances (one per `entropic_hook_point_t` value, `ENTROPIC_HOOK_COUNT_` = 23 per `include/entropic/types/hooks.h:36-89`), so the **actual runtime mutex-object count is 40 singular objects + 23 array elements = 63**.

**Confidence: high on the 41-declaration count for `src/`+`include/`, moderate on "63 objects total is the complete picture."** I verified by (a) grepping declarations separately from lock-site usages and checking every lock site's target name resolves to a declaration I found, and (b) confirming no `pthread_mutex_t`/atomic-based spinlocks exist in first-party code. I did **not** exhaustively check for mutexes constructed dynamically at runtime (e.g., inside a container resized at runtime, or `std::vector<std::mutex>`) beyond the one array case found — a per-request or per-connection dynamically-allocated mutex would not show up as a simple field grep. I also deliberately excluded `extern/llama.cpp` (vendored, not "entropic's own" code) and `tests/` — if the question intends those in scope, the vendored tree alone adds ~50+ more mutex declarations (see grep output), which I did not attempt to fully deduplicate/count.

## Gaps

- Did not check for dynamically-sized mutex collections (e.g., a mutex per connection/session allocated in a container at runtime) beyond the one `std::array` case found; a grep for fixed declarations cannot see those.
- Did not include `extern/llama.cpp` vendored mutexes in the count — treated as out of scope for "entropic['s] engine," but the repo does statically link/build against them, so if the benchmark intends the whole build tree, the number is materially higher (see the earlier grep output for that subtree).
- Did not build/run the code or use a static analyzer (e.g., clang-tidy `thread-safety` annotations) to verify no `TSA_GUARDED_BY` annotations exist that I might have missed by name-based grep alone — I did not find any `GUARDED_BY` usage in the source I read, but did not exhaustively search for it.
