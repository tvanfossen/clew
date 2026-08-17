# Q2 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll analyze the entropic repository to identify cases where two mutexes are held simultaneously and whether the acquisition order is consistent.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/entropic -type f \( -name "*.cpp" -o -name "*.h" -o -name "*.hpp" \) | head -20
- **got:** ~/ddb-targets/entropic/src/facade/entropic_compaction.cpp ~/ddb-targets/entropic/src/facade/entropic_mcp.cpp ~/ddb-targets/entropic/src/facade/engine_handle.h ~/ddb-targets/entropic/src/facade/entropic_audit.cpp ~/ddb-ta…

### 2. `Grep`
- **asked:** pattern=std::mutex|std::shared_mutex|std::lock_guard|std::unique_lock|std::scoped_lock
- **got:** No files found

### 3. `Grep`
- **asked:** pattern=pthread_mutex|mutex|lock|critical
- **got:** No files found

### 4. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic && find . -type f -name "*.h" -o -name "*.hpp" | xargs grep -l "mutex\|lock\|Lock\|LOCK" 2>/dev/null | head -20
- **got:** ./src/facade/engine_handle.h ./src/inference/llama_cpp_backend.h ./src/inference/llama_cpp_sampler.h ./src/inference/mtp_envelope.h ./src/inference/adapters/nemotron3_adapter.h ./src/inference/adapters/qwen36_adapter.h .…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/engine_handle.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file engine_handle.h 4	 * @brief Private definition of the entropic_engine struct. 5	 * 6	 * The public C API uses `entropic_handle_t` (opaque pointer to 7	 * `struct …

### 6. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file llama_cpp_backend.h 4	 * @brief LlamaCppBackend — llama.cpp C API integration. 5	 * 6	 * Versioned subclass pattern: LlamaCppBackend provides common llama.cpp 7	 …

### 7. `Bash`
- **asked:** command=find . -type f \( -name "*.cpp" -o -name "*.h" \) ! -path "./extern/*" -exec grep -l "lock_guard\|unique_lock\|scoped_lock" {} \;
- **got:** ./src/facade/engine_handle.h ./src/facade/external_bridge.cpp ./src/types/logging.cpp ./src/core/compactor_registry.cpp ./src/core/engine.cpp ./src/core/identity_manager.cpp ./src/core/constitutional_validator.cpp ./src/…

### 8. `Bash`
- **asked:** command=grep -n "lock_guard\|unique_lock\|scoped_lock" src/inference/llama_cpp_backend.cpp | head -40
- **got:** 622:    std::lock_guard<std::mutex> lk(mtp_mutex_); 746:    std::lock_guard<std::mutex> lk(mtp_mutex_); 915:    std::lock_guard<std::mutex> lock(seq_id_mutex_); 931:    std::lock_guard<std::mutex> lock(seq_id_mutex_); 39…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 610	 * the tier-switch reload. The old "keep GPU model on CPU-reload 611	 * failure" fallback is dropped — it left VRAM pinned, contradicting the 612	 * deactivation; a failed warm-reload now nulls the handle (recoverabl…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 730	 * @internal 731	 * @version 2.3.10 732	 */ 733	void LlamaCppBackend::inject_sampler_factory_for_test( 734	    std::unique_ptr<SamplerFactory> factory) 735	{ 736	    sampler_factory_ = std::move(factory); 737	} 738	 …

### 11. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 900	 * @brief Allocate a temporary sequence ID for evaluation. 901	 * 902	 * Reuses a released id from the pool, else mints a fresh monotonic id. 903	 * gh#98 (v2.8.0): the old `1 + free_seq_ids_.size()` returned 1 on EV…

### 12. `Bash`
- **asked:** command=grep -n "allocate_temp_seq_id\|release_temp_seq_id\|setup_mtp\|generate_mtp" src/inference/llama_cpp_backend.cpp | head -30
- **got:** 523: *       already-locked generate_mtp→setup_mtp_draft rebuild path, so locking 524: *       here would self-deadlock. Callers that race generate_mtp 554:bool LlamaCppBackend::setup_mtp_draft(const std::string& head_pa…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 1670	    b.logits[k] = want_logits ? 1 : 0; 1671	} 1672	 1673	/** 1674	 * @brief Build per-request sampler chains + KV sequence ids (gh#98). 1675	 * @return false if any sampler chain could not be built. 1676	 * @interna…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 3900	 * deactivate/unload teardown cannot free mtp_draft_ctx_ mid-flight (gh#58 UAF). 3901	 * Fails loudly (no plain-decode fallback) when the request is outside the MTP 3902	 * envelope — see mtp_guard / mtp_unsupported…

### 15. `Bash`
- **asked:** command=grep -n "do_generate_batch\|run_batched_decode" src/inference/llama_cpp_backend.cpp | head -20
- **got:** 1849:std::vector<GenerationResult> LlamaCppBackend::run_batched_decode( 1903:std::vector<GenerationResult> LlamaCppBackend::do_generate_batch( 1920:        return InferenceBackend::do_generate_batch(requests, params, can…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 1849	std::vector<GenerationResult> LlamaCppBackend::run_batched_decode( 1850	    const std::vector<std::vector<llama_token>>& toks, 1851	    const std::vector<GenerationParams>& params, 1852	    std::size_t shared, 1853	…

### 17. `Bash`
- **asked:** command=grep -n "mtp_run_from_tokens" src/inference/llama_cpp_backend.cpp
- **got:** 3832:GenerationResult mtp_run_from_tokens( 3928:    return mtp_run_from_tokens(ctx_, mtp_draft_ctx_, model_, tokens, params,

### 18. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 3832	GenerationResult mtp_run_from_tokens( 3833	    llama_context* ctx_tgt, llama_context* ctx_dft, llama_model* model_tgt, 3834	    const std::vector<llama_token>& tokens, const GenerationParams& params, 3835	    std::f…

### 19. `Bash`
- **asked:** command=grep -n "api_mutex\|lock_guard\|unique_lock" src/facade/entropic.cpp | head -40
- **got:** 138: * @brief Read the per-handle last_error under api_mutex. 234: * members (hook_registry, api_mutex, last_error, state flags). 1984:    // gh#109: log scope only (no api_mutex) — a long turn must not block 2080:    //…

### 20. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 2610	    if (!handle) { return ENTROPIC_ERROR_INVALID_HANDLE; } 2611	    if (!handle->engine) { return ENTROPIC_ERROR_INVALID_STATE; } 2612	    handle->engine->interrupt(); 2613	    return ENTROPIC_OK; 2614	} 2615	 2616	…

### 21. `Bash`
- **asked:** command=grep -B 3 -A 3 "HandleApiLock\|lock_guard.*api_mutex" src/facade/entropic.cpp | head -60
- **got:** */ extern "C" const char* entropic_last_error(entropic_handle_t handle) {     if (!handle) { return s_pre_create_error; }     entropic::HandleApiLock lock(handle);  // gh#59 v2.3.1: mutex + log scope     s_last_error_cac…

### 22. `Bash`
- **asked:** command=grep -n "HandleApiLock\|api_mutex\|mtp_mutex_\|seq_id_mutex_" src/core/engine.cpp | head -40
- **got:** (Bash completed with no output)

### 23. `Bash`
- **asked:** command=grep -n "lock_guard\|unique_lock\|scoped_lock" src/inference/orchestrator.cpp | head -30
- **got:** 1020:    std::lock_guard<std::mutex> lock(swap_mutex_); 1716:    std::lock_guard<std::mutex> lock(swap_mutex_); 1732:    std::lock_guard<std::mutex> lock(swap_mutex_); 1803:    std::lock_guard<std::mutex> lock(swap_mutex…

### 24. `Bash`
- **asked:** command=grep -n "swap_mutex_" include/entropic/inference/orchestrator.h
- **got:** 559:    mutable std::mutex swap_mutex_;  ///< Guards tier swap + residency mutations

### 25. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1010	 * unknown), reuses a hot backend or admits + activates a cold one 1011	 * through the residency gate. Returns nullptr on a refused activation 1012	 * (with `last_residency_error_` set) or on a real load failure. 10…

### 26. `Bash`
- **asked:** command=grep -A 100 "void LlamaCppBackend::do_deactivate" src/inference/llama_cpp_backend.cpp | grep -E "allocate_temp_seq_id|release_temp_seq_id|seq_id_mutex_"
- **got:** (Bash completed with no output)

### 27. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 1820	        r.token_count = s.n_gen; 1821	        r.finish_reason = s.finish; 1822	        out.push_back(std::move(r)); 1823	    } 1824	    return out; 1825	} 1826	 1827	/** 1828	 * @brief Release every batch sequence's…

### 28. `Bash`
- **asked:** command=find src -name "*.cpp" -type f ! -path "*/extern/*" -exec grep -l "lock_guard\|unique_lock" {} \; | while read f; do echo "=== $f ==="; grep -n "lock_guard\|unique_lock" "$f"; done | grep -A 30 "llama_cpp_backend.cpp"
- **got:** === src/inference/llama_cpp_backend.cpp === 622:    std::lock_guard<std::mutex> lk(mtp_mutex_); 746:    std::lock_guard<std::mutex> lk(mtp_mutex_); 915:    std::lock_guard<std::mutex> lock(seq_id_mutex_); 931:    std::lo…

### 29. `Bash`
- **asked:** command=grep -n "entropic_run\|HandleApiLock" src/facade/entropic.cpp | head -40
- **got:** 152:    entropic::HandleApiLock lock(handle);  // gh#59 v2.3.1: mutex + log scope 1756:    entropic::HandleApiLock lock(handle);  // gh#59 v2.3.1: mutex + log scope 1805:    entropic::HandleApiLock lock(handle);  // gh#5…

### 30. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 1974	entropic_error_t entropic_run( 1975	    entropic_handle_t handle, 1976	    const char* input, 1977	    char** result_json) { 1978	    auto rc = check_orchestrator(handle); 1979	    if (rc != ENTROPIC_OK || !input ||…

### 31. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 3906	GenerationResult LlamaCppBackend::generate_mtp( 3907	    const std::vector<Message>& messages, 3908	    const GenerationParams& params, 3909	    std::function<void(std::string_view)> on_token, 3910	    std::atomic<b…

### 32. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 2222	entropic_error_t entropic_run_streaming( 2223	    entropic_handle_t handle, 2224	    const char* input, 2225	    void (*on_token)(const char* token, size_t len, void* user_data), 2226	    void* user_data, 2227	    i…

### 33. `Bash`
- **asked:** command=for f in $(find src -name "*.cpp" ! -path "*/extern/*" -type f); do   lines=$(grep -n "lock_guard\|unique_lock\|scoped_lock" "$f" | wc -l)   if [ "$lines" -gt 1 ]; then     echo "=== $f ($lines locks) ==="     grep -n "lock_guard\|unique_lock\|scoped_lock" "$f"   fi done
- **got:** === src/facade/external_bridge.cpp (19 locks) === 393:    std::lock_guard<std::mutex> lock(bridge->tasks_mutex_); 412:    std::lock_guard<std::mutex> lock(bridge->tasks_mutex_); 495:    std::lock_guard<std::mutex> lock(t…

### 34. `Bash`
- **asked:** command=grep -B 50 "std::lock_guard.*tasks_mutex_" src/facade/external_bridge.cpp | grep -A 50 "void\|GenerationResult\|bool\|std::string" | head -80
- **got:** std::string text;     ///< result or error message };  /**  * @brief Translate entropic_run's return code into a final task state.  *  * On success, extracts the final clean assistant text from result_json  * and frees i…

### 35. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/external_bridge.cpp
- **got:** 760	    // crashed-prior-process recovery, but if a live in-process bridge 761	    // owned that file, the unlink stole its binding silently. The 762	    // claim must happen *before* create_listen_socket so a concurrent…

### 36. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/engine.cpp
- **got:** 230	 * @param user_data Forwarded to both callbacks. 231	 * @internal 232	 * @version 2.1.6 233	 */ 234	void AgentEngine::set_delegation_callbacks( 235	    ent_decision_t (*on_start)(const ent_delegation_request_t*, void…

### 37. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/engine.cpp
- **got:** 3175	} 3176	 3177	// ── Mid-generation user-message queue (gh#40, v2.1.10) ───────── 3178	 3179	/** 3180	 * @brief Enqueue a user message subject to the configured cap. 3181	 * @internal 3182	 * @version 2.1.10 3183	 */ …

### 38. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 150	 * ignoring the auto_retry_enabled_ flag for this call, and stores the 151	 * final result. Returns INVALID_STATE if no pending state exists. 152	 * 153	 * @return ENTROPIC_OK on success, INVALID_STATE if nothing pau…

### 39. `Bash`
- **asked:** command=grep -A 15 "void ConstitutionalValidator::store_result" src/core/constitutional_validator.cpp | head -25
- **got:** void ConstitutionalValidator::store_result(     const ValidationResult& result) {     std::lock_guard<std::mutex> lock(result_mutex_);     last_result_ = result; }  /**  * @brief Run the core validation loop (critique + …

### 40. `Bash`
- **asked:** command=find src -name "*.cpp" ! -path "*/extern/*" -type f -exec grep -l "lock_guard\|unique_lock" {} \; | while read f; do   awk '   /std::lock_guard|std::unique_lock|std::scoped_lock/ {     match($0, /lock_guard<|unique_lock<|scoped_lock</)     if (RSTART) {       indent_level = match($0, /[^ ]/) - 1       if (last_indent != -1 && last_indent == indent_level) {         print FILENAME ":" NR ": Possible nested lock at same indent level as previous"         print prev_line         print $0       }       last_indent = indent_level       prev_line = FILENAME ":" NR ": " $0     }   }   ' "$f" done | head -50
- **got:** src/facade/external_bridge.cpp:412: Possible nested lock at same indent level as previous src/facade/external_bridge.cpp:393:     std::lock_guard<std::mutex> lock(bridge->tasks_mutex_);     std::lock_guard<std::mutex> lo…

### 41. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 95	 * @return true if validation should run. 96	 * @internal 97	 * @version 2.0.7 98	 */ 99	bool ConstitutionalValidator::should_validate( 100	    const std::string& identity_name) const { 101	    std::lock_guard<std::mu…

### 42. `Bash`
- **asked:** command=awk ' /std::lock_guard|std::unique_lock|std::scoped_lock/ {   # Track lock acquisitions with their brace level   lock_info = $0   match($0, /\b(lock_guard|unique_lock|scoped_lock)<.*?>(.*?)/)   mutex_name = $0   gsub(/.*\(/, "", mutex_name)   gsub(/\).*/, "", mutex_name)      # Count braces to track nesting   for (i = 1; i <= length($0); i++) {     c = substr($0, i, 1)     if (c == "{") brace_depth++     else if (c == "}") brace_depth--   }      print FILENAME ":" NR ": brace_depth=" brace_depth " mutex=" mutex_name } ' src/facade/external_bridge.cpp | head -30
- **got:** src/facade/external_bridge.cpp:393: brace_depth= mutex=bridge->tasks_mutex_ src/facade/external_bridge.cpp:412: brace_depth= mutex=bridge->tasks_mutex_ src/facade/external_bridge.cpp:495: brace_depth= mutex=tasks_mutex_ …

### 43. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/health_monitor.cpp
- **got:** 130	} 131	 132	/** 133	 * @brief Background monitor loop. 134	 * @callback 135	 * @version 1.8.7 136	 */ 137	void HealthMonitor::monitor_loop() { 138	    constexpr auto poll_interval = std::chrono::milliseconds(500); 139…

### 44. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1019	InferenceBackend* ModelOrchestrator::get_model(const std::string& tier_name) { 1020	    std::lock_guard<std::mutex> lock(swap_mutex_); 1021	 1022	    auto it = tiers_.find(tier_name); 1023	    std::string effective_…

### 45. `Bash`
- **asked:** command=grep -A 20 "void ModelOrchestrator::deactivate_current_if_needed" src/inference/orchestrator.cpp
- **got:** void ModelOrchestrator::deactivate_current_if_needed(InferenceBackend* incoming) {     auto it = loaded_main_tier_.empty()         ? tiers_.end() : tiers_.find(loaded_main_tier_);      bool should_swap = it != tiers_.end…

### 46. `Bash`
- **asked:** command=grep -A 20 "void ModelOrchestrator::unload_or_warm_current" src/inference/orchestrator.cpp
- **got:** void ModelOrchestrator::unload_or_warm_current(InferenceBackend* current) {     auto cfg_it = config_.models.tiers.find(loaded_main_tier_);     bool keep_warm = cfg_it != config_.models.tiers.end()         && cfg_it->sec…

**Reasoning.** Now I can formulate a comprehensive answer. Let me verify the key finding by looking at the call chain one more time.

### 47. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1068	 * 1069	 * keep_warm=true → WARM. keep_warm=false → COLD. v2.2.4 (gh#57): the 1070	 * COLD-path unload fires a `ResidencyEvent::Evicted` so the residency 1071	 * observer sees every "tier model just left VRAM" trans…

### 48. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1710	 * @brief Public footprint accessor — memoizes via tier_footprint_bytes_. 1711	 * @internal 1712	 * @version 2.2.4 1713	 */ 1714	size_t ModelOrchestrator::tier_footprint_bytes( 1715	    const std::string& tier_name)…

### 49. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1795	} 1796	 1797	/** 1798	 * @brief Serialize the current VRAM residency snapshot to JSON. 1799	 * @internal 1800	 * @version 2.3.7 1801	 */ 1802	std::string ModelOrchestrator::residency_snapshot_json() const { 1803	   …

### 50. `Bash`
- **asked:** command=grep -B 10 "mtp_mutex_" src/inference/llama_cpp_backend.cpp | grep -E "^\s*(bool|void|GenerationResult|auto|std::|if|else|for|while|try|catch)" | grep -E "^\s*(bool|void|GenerationResult)" | tail -10
- **got:** void LlamaCppBackend::do_deactivate() { void LlamaCppBackend::do_unload() { GenerationResult LlamaCppBackend::generate_mtp(

### 51. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.cpp
- **got:** 3906	GenerationResult LlamaCppBackend::generate_mtp( 3907	    const std::vector<Message>& messages, 3908	    const GenerationParams& params, 3909	    std::function<void(std::string_view)> on_token, 3910	    std::atomic<b…

### 52. `Bash`
- **asked:** command=grep -A 100 "GenerationResult mtp_run_from_tokens" src/inference/llama_cpp_backend.cpp | grep -E "allocate_temp_seq_id|release_temp_seq_id|seq_id"
- **got:** (Bash completed with no output)

**Reasoning.** ## Summary

I found **one case where entropic holds two mutexes at once**, and the acquisition order is **consistent**.

## Cases Found

### Case 1: `swap_mutex_` + `mtp_mutex_` (HIGH CONFIDENCE)

**Call Path:**
1. `ModelOrchestrator::get_model()` acquires `swap_mutex_` at orchestrator.cpp:1020
2. Calls `deactivate_current_if_needed()` at orchestrator.cpp:1037
3. Which calls `unload_or_warm_current()` at orchestrator.cpp:1097
4. Which calls either `backend->deactivate()` (orchestrator.cpp:1007) or `backend->unload()` (orchestrator.cpp:1016)
5. `LlamaCppBackend::do_deactivate()` acquires `mtp_m

---

## Final answer as submitted

## Summary

I found **one case where entropic holds two mutexes at once**, and the acquisition order is **consistent**.

## Cases Found

### Case 1: `swap_mutex_` + `mtp_mutex_` (HIGH CONFIDENCE)

**Call Path:**
1. `ModelOrchestrator::get_model()` acquires `swap_mutex_` at orchestrator.cpp:1020
2. Calls `deactivate_current_if_needed()` at orchestrator.cpp:1037
3. Which calls `unload_or_warm_current()` at orchestrator.cpp:1097
4. Which calls either `backend->deactivate()` (orchestrator.cpp:1007) or `backend->unload()` (orchestrator.cpp:1016)
5. `LlamaCppBackend::do_deactivate()` acquires `mtp_mutex_` at llama_cpp_backend.cpp:622
6. `LlamaCppBackend::do_unload()` acquires `mtp_mutex_` at llama_cpp_backend.cpp:746

**Both mutexes held simultaneously:** YES - `swap_mutex_` is held throughout the entire `unload_or_warm_current()` call while `mtp_mutex_` is acquired within the backend methods.

**Acquisition Order Consistency:** CONSISTENT
- Only one ordering path exists: `swap_mutex_` → `mtp_mutex_`
- `generate_mtp()` (the only other place `mtp_mutex_` is acquired at llama_cpp_backend.cpp:3915) doesn't call orchestrator methods that would acquire `swap_mutex_`
- No reverse ordering (mtp → swap) exists, so no deadlock risk

**Why:** The comment at llama_cpp_backend.cpp:619-621 explains this is intentional: "`gh#108: serialise vs an in-flight generate_mtp — it holds mtp_mutex_ across its decode, so this blocks until that decode finishes before freeing the MTP head + ctx_`"

## Gaps

I could not definitively verify:
- Whether there are any paths where `seq_id_mutex_` and `mtp_mutex_` are held together (though my analysis suggests they're not - mtp generation doesn't allocate batch seq_ids)
- Whether any other subsystem mutexes (from engine, constitutional validator, storage, or MCP layers) interact with the backend mutexes in a two-mutex pattern
