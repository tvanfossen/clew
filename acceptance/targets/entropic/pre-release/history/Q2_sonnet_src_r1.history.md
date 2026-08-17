# Q2 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic && grep -rn "std::mutex\|std::lock_guard\|std::unique_lock\|std::scoped_lock\|std::lock(" --include=*.hpp --include=*.cpp --include=*.h -l | grep -v extern | grep -v build
- **got:** src/facade/engine_handle.h src/types/logging.cpp src/core/compactor_registry.cpp src/core/engine.cpp src/core/identity_manager.cpp src/core/constitutional_validator.cpp src/core/hook_registry.cpp src/inference/throughput…

### 2. `Agent`
- **asked:** description, prompt, subagent_type
- **got:** Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.) agentId: a5e38f75dd8b4d9d8 (internal ID - do not me…

**Reasoning.** Let me also do some direct investigation while the agent works, in case its findings need cross-checking.

### 3. `Bash`
- **asked:** command=grep -rn "std::mutex\|std::recursive_mutex\|std::shared_mutex" include/ src/ --include=*.h --include=*.hpp | grep -v "//"
- **got:** include/entropic/core/engine.h:1425:    mutable std::mutex delegation_cb_mutex_; include/entropic/core/constitutional_validator.h:627:    mutable std::mutex attempt_boundary_mutex_; include/entropic/core/constitutional_v…

### 4. `Bash`
- **asked:** command=grep -rn "mutex" include/entropic/inference/adapter_manager.h include/entropic/inference/backend.h include/entropic/inference/throughput_tracker.h include/entropic/storage/audit_logger.h include/entropic/storage/permission_persister.h include/entropic/storage/database.h include/entropic/mcp/health_monitor.h include/entropic/mcp/transport_sse.h include/entropic/mcp/transport_stdio.h 2>/dev/null
- **got:** include/entropic/inference/adapter_manager.h:14: * - State queries require the class mutex (AdapterEntry::state) include/entropic/inference/adapter_manager.h:15: * - load/unload/swap acquire adapter_mutex_ include/entrop…

### 5. `Bash`
- **asked:** command=grep -n "adapter_mutex_\|transition_mutex_\|lock_guard\|unique_lock\|scoped_lock" src/inference/adapter_manager.cpp
- **got:** 79:    std::lock_guard<std::mutex> lock(adapter_mutex_); 126:    std::lock_guard<std::mutex> lock(adapter_mutex_); 165:    std::lock_guard<std::mutex> lock(adapter_mutex_); 209:    std::lock_guard<std::mutex> lock(adapte…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/adapter_manager.cpp
- **got:** 230	 * @brief Swap to a different adapter atomically. 231	 * 232	 * Deactivates current HOT adapter and activates the target. 233	 * Fires ON_ADAPTER_SWAP hook which can cancel the operation. 234	 * 235	 * @param name Ta…

### 7. `Bash`
- **asked:** command=grep -n "transition_mutex_\|adapter_mutex_\|swap(\|unload_all\|lock_guard\|unique_lock" src/inference/orchestrator.cpp src/inference/backend.cpp | head -80
- **got:** src/inference/orchestrator.cpp:270:    lora_manager_.unload_all(); src/inference/orchestrator.cpp:1020:    std::lock_guard<std::mutex> lock(swap_mutex_); src/inference/orchestrator.cpp:1092:        lora_manager_.unload_a…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1000	    fire_residency_observer(ResidencyEvent::Loaded, 1001	                            tier_name, tier_it->second.path.string(), 1002	                            footprint); 1003	    return backend.get(); 1004	} 1005	…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1106	void ModelOrchestrator::unload_or_warm_current(InferenceBackend* current) { 1107	    auto cfg_it = config_.models.tiers.find(loaded_main_tier_); 1108	    bool keep_warm = cfg_it != config_.models.tiers.end() 1109	  …

### 10. `Bash`
- **asked:** command=grep -n "activate_and_track\|residency_admits\|record_activation_reuse" src/inference/orchestrator.cpp | head -20
- **got:** 890:void ModelOrchestrator::record_activation_reuse( 919:bool ModelOrchestrator::residency_admits(const std::string& tier_name) { 983:InferenceBackend* ModelOrchestrator::activate_and_track( 1034:        record_activatio…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 890	void ModelOrchestrator::record_activation_reuse( 891	    const std::string& tier_name) { 892	    auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>( 893	        std::chrono::steady_clock::now() - sta…

### 12. `Bash`
- **asked:** command=grep -n "load_and_activate\|::load(\|::activate(\|::deactivate(\|::unload(" src/inference/backend.cpp include/entropic/inference/backend.h
- **got:** src/inference/backend.cpp:54:bool InferenceBackend::load(const ModelConfig& config) { src/inference/backend.cpp:88:bool InferenceBackend::activate() { src/inference/backend.cpp:117:void InferenceBackend::deactivate() { s…

**Reasoning.** This confirms the nesting chain. Let me wait for the Explore agent's comprehensive findings before writing the final answer, since it's covering the same ground plus health_monitor and constitutional_validator areas.

### 13. `Bash`
- **asked:** command=sed -n '160,190p' ~/ddb-targets/entropic/src/inference/backend.cpp
- **got:** * @param config Model config.  * @return true on success.  * @internal  * @version 1.8.2  */ bool InferenceBackend::load_and_activate(const ModelConfig& config) {     if (!load(config)) {         return false;     }     …

### 14. `Bash`
- **asked:** command=grep -n "attempt_boundary_mutex_\|critique_cbs_mutex_\|lock_guard\|unique_lock" ~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 101:    std::lock_guard<std::mutex> lock(overrides_mutex_); 120:    std::lock_guard<std::mutex> lock(overrides_mutex_); 160:        std::lock_guard lock(pending_mutex_); 190:        std::lock_guard lock(pending_mutex_); …

### 15. `Bash`
- **asked:** command=grep -n "mutex" ~/ddb-targets/entropic/include/entropic/core/constitutional_validator.h
- **got:** 17: * - Per-identity overrides and global_enabled_ guarded by mutex 18: * - last_result_ guarded by mutex for concurrent access 44:#include <mutex> 268:     * @threadsafety Thread-safe (guarded by critique_cbs_mutex_). 5…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 140	 * @version 2.1.5 141	 */ 142	bool ConstitutionalValidator::auto_retry_enabled() const { 143	    return auto_retry_enabled_.load(); 144	} 145	 146	/** 147	 * @brief Resume the revision loop after a paused validation.…

### 17. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 495	    extract_violations(json_str, result); 496	    extract_revised_field(json_str, result); 497	    return result; 498	} 499	 500	// ── Private Implementation ──────────────────────────────── 501	 502	/** 503	 * @brie…

### 18. `Bash`
- **asked:** command=grep -n "watched_mutex_\|event_mutex_\|wake_mutex_\|lock_guard\|unique_lock" ~/ddb-targets/entropic/src/mcp/health_monitor.cpp
- **got:** 48:    std::lock_guard<std::mutex> lock(watched_mutex_); 67:    std::lock_guard<std::mutex> lock(watched_mutex_); 121:        std::lock_guard<std::mutex> lock(event_mutex_); 142:            std::lock_guard<std::mutex> lo…

### 19. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/health_monitor.cpp
- **got:** 95	} 96	 97	/** 98	 * @brief Stop monitoring and all reconnection attempts. 99	 * @internal 100	 * @version 1.8.7 101	 */ 102	void HealthMonitor::stop() { 103	    if (!running_.exchange(false)) { 104	        return; 105	…

### 20. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/health_monitor.cpp
- **got:** 164	void HealthMonitor::check_server( 165	    const std::string& name, 166	    WatchEntry& entry) { 167	 168	    bool alive = entry.client->is_connected(); 169	 170	    if (entry.status == "connected" && !alive) { 171	  …

### 21. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1690	 * 1691	 * @internal 1692	 * @version 2.2.4 1693	 */ 1694	size_t ModelOrchestrator::estimate_footprint_bytes( 1695	    const std::string& tier_name) const { 1696	    auto tier_it = config_.models.tiers.find(tier_nam…

**Reasoning.** These are fine — self-contained, no nesting risk. Now let me check the Explore agent's results.

### 22. `Bash`
- **asked:** command=sleep 30
- **got ⚠ error:** <tool_use_error>Blocked: standalone sleep 30. To wait for a condition, use Monitor with an until-loop (e.g. `until <check>; do sleep 2; done`). To wait for a command you started, use run_in_background: true. Do not chain…

### 23. `Bash`
- **asked:** command=grep -n "mutexes_\[\|shared_lock\|unique_lock\|lock_guard" ~/ddb-targets/entropic/src/core/hook_registry.cpp | head -40
- **got:** 51:    std::unique_lock lock(mutexes_[idx]); 87:    std::unique_lock lock(mutexes_[idx]); 113:    std::shared_lock lock(mutexes_[idx]); 271:    std::shared_lock lock(mutexes_[idx]);

### 24. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/hook_registry.cpp
- **got:** 95	 96	    if (it != vec.end()) { 97	        vec.erase(it); 98	        logger->info("Deregistered hook: point={}", static_cast<int>(point)); 99	    } 100	    return ENTROPIC_OK; 101	} 102	 103	/** 104	 * @brief Take a sn…

### 25. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/hook_registry.cpp
- **got:** 126	int HookRegistry::fire_pre( 127	    entropic_hook_point_t point, 128	    const char* context_json, 129	    char** out_json) { 130	    *out_json = nullptr; 131	 132	    if (!is_valid_point(point)) { 133	        return…

**Reasoning.** Confirmed — good design, no nesting here. Now checking if the background agent has finished.

### 26. `Bash`
- **asked:** command=grep -rn "lock_guard\|unique_lock\|scoped_lock" ~/ddb-targets/entropic/src/mcp/mcp_authorization.cpp ~/ddb-targets/entropic/src/mcp/mcp_key_set.cpp ~/ddb-targets/entropic/src/core/identity_manager.cpp ~/ddb-targets/entropic/src/core/compactor_registry.cpp ~/ddb-targets/entropic/src/core/engine.cpp 2>/dev/null
- **got:** ~/ddb-targets/entropic/src/mcp/mcp_authorization.cpp:25:    std::lock_guard<std::mutex> lock(auth_mutex_); ~/ddb-targets/entropic/src/mcp/mcp_authorization.cpp:39:    std::lock_guard<std::mutex> lock(auth_mutex_); ~/ddb-…

**Reasoning.** Single-mutex classes, no nesting concern there. Let me wait for the Explore agent since it may have found things I missed (transport_sse, transport_stdio, external_bridge, secondary_model_loader).

### 27. `Bash`
- **asked:** command=grep -n "mutex\|lock_guard\|unique_lock\|scoped_lock" ~/ddb-targets/entropic/src/mcp/transport_sse.cpp ~/ddb-targets/entropic/src/mcp/transport_stdio.cpp ~/ddb-targets/entropic/include/entropic/mcp/external_bridge.h 2>/dev/null | head -60
- **got:** ~/ddb-targets/entropic/src/mcp/transport_sse.cpp:198:    std::unique_lock<std::mutex> lock(pending_mutex_); ~/ddb-targets/entropic/src/mcp/transport_sse.cpp:328:            std::lock_guard<std::mutex> lock(pending_mutex_…

### 28. `Bash`
- **asked:** command=find ~/ddb-targets/entropic -name "external_bridge*"
- **got:** ~/ddb-targets/entropic/src/facade/external_bridge.cpp ~/ddb-targets/entropic/tests/unit/mcp/external_bridge_test.cpp ~/ddb-targets/entropic/include/entropic/mcp/external_bridge.h

### 29. `Bash`
- **asked:** command=grep -n "tasks_mutex_\|subscribers_mutex_\|client_threads_mutex_\|lock_guard\|unique_lock\|notify_subscribers\|phase_observer_cb" ~/ddb-targets/entropic/src/facade/external_bridge.cpp
- **got:** 393:    std::lock_guard<std::mutex> lock(bridge->tasks_mutex_); 412:    std::lock_guard<std::mutex> lock(bridge->tasks_mutex_); 495:    std::lock_guard<std::mutex> lock(tasks_mutex_); 770:        std::lock_guard lk(s_bou…

### 30. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/external_bridge.cpp
- **got:** 1060	    else if (method == "shutdown" || method == "exit") { result = json::object(); } 1061	    else { return rpc_err(id, -32601, "Unknown method: " + method); } 1062	    return rpc_ok(id, result); 1063	} 1064	 1065	//…

### 31. `Bash`
- **asked:** command=grep -n "mutex" ~/ddb-targets/entropic/include/entropic/inference/prompt_cache.h ~/ddb-targets/entropic/src/inference/prompt_cache.cpp 2>/dev/null
- **got ⚠ error:** Exit code 2 ~/ddb-targets/entropic/src/inference/prompt_cache.cpp:95:    std::lock_guard<std::mutex> lock(mutex_); ~/ddb-targets/entropic/src/inference/prompt_cache.cpp:155:    std::lock_guard<std::mutex> lock(mutex_); ~…

**Reasoning.** Single mutex, fine. Let me check the storage layer (database + permission_persister + audit_logger interplay).

### 32. `Bash`
- **asked:** command=grep -n "lock_guard\|unique_lock\|mutex_\.\|write_mutex_" ~/ddb-targets/entropic/src/storage/database.cpp ~/ddb-targets/entropic/src/storage/permission_persister.cpp ~/ddb-targets/entropic/src/storage/audit_logger.cpp
- **got:** ~/ddb-targets/entropic/src/storage/database.cpp:184:    std::lock_guard lock(mutex_); ~/ddb-targets/entropic/src/storage/database.cpp:222:    std::lock_guard lock(mutex_); ~/ddb-targets/entropic/src/storage/database.cpp:…

### 33. `Bash`
- **asked:** command=sed -n '200,260p' ~/ddb-targets/entropic/src/storage/permission_persister.cpp
- **got:** // iterator-invalidation rules), so the second insert ran on a         // stale iterator (UB; surfaces as SIGSEGV on glibc). Now we         // insert the sub-key (`  deny:` or `  allow:`) first, then the         // item …

### 34. `Bash`
- **asked:** command=echo checking
- **got:** checking

### 35. `Bash`
- **asked:** command=sed -n '3170,3245p' ~/ddb-targets/entropic/src/core/engine.cpp
- **got:** * @internal  * @version 2.0.2  */ const std::vector<Message>& AgentEngine::get_messages() const {     return conversation_; }  // ── Mid-generation user-message queue (gh#40, v2.1.10) ─────────  /**  * @brief Enqueue a u…

### 36. `Bash`
- **asked:** command=sed -n '185,340p' ~/ddb-targets/entropic/src/mcp/transport_sse.cpp
- **got:** }  /**  * @brief Wait for SSE response with matching request ID.  * @param request_id JSON-RPC request ID to match.  * @param timeout_ms Maximum wait time.  * @return Response string, or empty on timeout/disconnect.  * @…

**Reasoning.** No cross-mutex nesting here — single mutex, no cross-object calls while held. This gives me solid confirmation. Let me now check for the Explore agent's completion before finalizing.

### 37. `Bash`
- **asked:** command=ls -la /tmp/claude-1000/-home-tvanfossen-Projects-docs-db--claude-tmp-bench-p7-entropic-wd/f9a84014-828b-4745-a32d-639b63ec5009/tasks/ 2>/dev/null
- **got:** total 12 drwxrwxr-x 2 tvanfossen tvanfossen 4096 Aug 15 21:24 . drwxrwxr-x 3 tvanfossen tvanfossen 4096 Aug 15 21:22 .. lrwxrwxrwx 1 tvanfossen tvanfossen  177 Aug 15 21:22 a5e38f75dd8b4d9d8.output -> ~/.claude/projects/…

### 38. `Bash`
- **asked:** command=grep -n "adapter\|lora_manager" ~/ddb-targets/entropic/src/inference/backend.cpp | head -20
- **got:** (Bash completed with no output)

**Reasoning.** Good — backend.cpp never touches AdapterManager, confirming `adapter_mutex_` and `transition_mutex_` never nest with each other directly, only each with `swap_mutex_`. That's sufficient corroboration. I'll finalize my answer now.

### 39. `Bash`
- **asked:** command=grep -n "class ModelOrchestrator\|swap_mutex_" ~/ddb-targets/entropic/include/entropic/inference/orchestrator.h
- **got:** 112:class ModelOrchestrator { 559:    mutable std::mutex swap_mutex_;  ///< Guards tier swap + residency mutations

**Reasoning.** ## Answer

**Yes — entropic has multiple places where two mutexes are held at once (always via one function calling into a second, mutex-guarded object while its own lock is still on the stack, i.e. nested/cross-object locking, not two `lock_guard`s in the same literal scope). In every case I found, the acquisition order is consistent: the same "outer" mutex is always taken first and never appears as the inner one relative to its partner.**

### Case 1 — `ModelOrchestrator::swap_mutex_` → `AdapterManager::adapter_mutex_`
- `ModelOrchestrator::get_model()` takes `swap_mutex_` for the whole func

**Reasoning.** The background agent's report just came in, and it both adds new findings and contradicts one of mine — let me quickly verify the disputed point and the new claims before updating my answer.

### 40. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic echo "--- health_monitor.cpp 137-155 (my claim: nested) ---" sed -n '137,155p' src/mcp/health_monitor.cpp echo "--- mtp_mutex_ in llama_cpp_backend ---" grep -n "mtp_mutex_\|do_deactivate\|do_unload" src/inference/llama_cpp_backend.cpp | head -20 echo "--- secondary_model_loader ---" grep -n "lock_guard\|unique_lock\|load_and_activate\|->unload\|->load\|->activate" src/inference/secondary_model_loader.cpp
- **got:** --- health_monitor.cpp 137-155 (my claim: nested) --- void HealthMonitor::monitor_loop() {     constexpr auto poll_interval = std::chrono::milliseconds(500);      while (running_) {         {             std::lock_guard<…

### 41. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic sed -n '40,100p' src/inference/backend.cpp echo "---adapter_manager swap fire_swap_hook---" sed -n '241,255p' src/inference/adapter_manager.cpp grep -n "fire_swap_hook\b" src/inference/adapter_manager.cpp
- **got:** } // anonymous namespace  // ── Lifecycle ──────────────────────────────────────────────  /**  * @brief Load model into CPU RAM (COLD → WARM).  *  * Acquires transition_mutex_. No-op if already WARM/ACTIVE.  *  * @param …

**Reasoning.** Confirmed. This corroborates the subagent's findings #5/#6 as well. Now I have a complete, cross-verified picture. Here's my consolidated final answer:

## Updated answer (incorporating a second-pass verification agent)

A background verification pass confirmed my findings, added three more real cases, and disputed one of my findings — I re-checked that dispute directly and my original citation stands. Consolidated result:

**Yes, entropic holds two mutexes at once in several places, and the order is consistent everywhere it's statically visible — with one structural caveat around hook callbac

---

## Final answer as submitted

Confirmed. This corroborates the subagent's findings #5/#6 as well. Now I have a complete, cross-verified picture. Here's my consolidated final answer:

## Updated answer (incorporating a second-pass verification agent)

A background verification pass confirmed my findings, added three more real cases, and disputed one of my findings — I re-checked that dispute directly and my original citation stands. Consolidated result:

**Yes, entropic holds two mutexes at once in several places, and the order is consistent everywhere it's statically visible — with one structural caveat around hook callbacks.**

### Confirmed nested-lock cases

1. **`ModelOrchestrator::swap_mutex_` → `AdapterManager::adapter_mutex_`** — `get_model()` holds `swap_mutex_` (`src/inference/orchestrator.cpp:1020`) across calls to `lora_manager_.unload_all_for_model()` (`:1092`→`src/inference/adapter_manager.cpp:295`) and `lora_manager_.swap()` (`:1280`→`adapter_manager.cpp:242`). **High confidence.**

2. **`ModelOrchestrator::swap_mutex_` → `InferenceBackend::transition_mutex_`** — same `get_model()` scope, via `deactivate()`/`unload()` (`src/inference/backend.cpp:118,140`) and `load()`/`activate()` (`:55,89`). **High confidence.**

3. **`HealthMonitor::watched_mutex_` → `HealthMonitor::event_mutex_`** — `monitor_loop()` holds `watched_mutex_` (`src/mcp/health_monitor.cpp:142-149`) while calling `check_server()`→`attempt_reconnect()`→`post_event()`/`on_reconnect_success()`, which lock `event_mutex_` (`:265`, `:291`). **High confidence — I re-verified this directly after a peer-review agent called this file "clean"; the peer review was wrong, my original line-by-line trace holds.**

4. **`SecondaryModelLoader::slots_mutex_` → `InferenceBackend::transition_mutex_`** (new, found by the review agent, verified by me) — `ensure_loaded()` holds `slots_mutex_` (`src/inference/secondary_model_loader.cpp:36`) across `backend->load_and_activate()` (`:48`); `release_role()`/`shutdown()` likewise hold `slots_mutex_` across `backend->unload()` (`:102`, `:163`). Same mutex pair/order as case 2, different outer lock. **High confidence.**

5. **`InferenceBackend::transition_mutex_` → `LlamaCppBackend::mtp_mutex_`** (new, verified) — `do_deactivate()` and `do_unload()` are called from within `transition_mutex_`-held `deactivate()`/`unload()`, and each explicitly takes `mtp_mutex_` (`src/inference/llama_cpp_backend.cpp:622`, `:746`), by design (gh#108, serializing against an in-flight `generate_mtp()` which itself holds `mtp_mutex_` alone at `:3915`, never `transition_mutex_`). **High confidence, and the order is deliberately one-directional per the code comments.**

6. **`transition_mutex_`/`adapter_mutex_` held across a `HookRegistry` callback invocation** (new, verified) — `InferenceBackend::load()` holds `transition_mutex_` while calling `fire_model_load_hook()` (`backend.cpp:63`), and `AdapterManager::swap()` holds `adapter_mutex_` while calling `fire_swap_hook()` (`adapter_manager.cpp:250`). `HookRegistry::fire_pre` itself only holds its per-point mutex briefly inside `snapshot()` before releasing it and invoking callbacks — so this isn't two registry mutexes at once — but it **is** an external, arbitrary callback running while a domain mutex is held. This is the one point where "consistent order" can't be fully verified statically: if any hook implementation (registered from outside this repo, e.g. a CLI/TUI/C-API consumer) re-enters the same backend or adapter manager, that's a same-thread self-deadlock, not just a lock-order question. **Medium-high confidence on the pattern; can't confirm or rule out a real inversion without seeing hook implementations, which live outside this repo.**

### Order consistency
Within `src/`/`include/`, every nesting found has a fixed, one-directional outer→inner relationship (`swap_mutex_`/`slots_mutex_` outer; `adapter_mutex_`/`transition_mutex_` inner; `transition_mutex_` outer to `mtp_mutex_`). No call path was found going the other way. The only unresolved risk is case 6, where control passes to code this repo doesn't contain.

## Gaps
- Hook callback implementations are outside this repo — case 6's real-world safety can't be confirmed from source alone.
- Not exhaustively traced: every `entropic_*` C API entrypoint against every internal lock (the review agent spot-checked `engine_handle.h`'s `api_mutex` and found comments indicating deliberate short-hold discipline, but did not check all ~30 facade functions line-by-line).
- Test-only mutexes (e.g. `tests/unit/mcp/transport_sse_test.cpp`) were excluded as out of scope for production behavior.
