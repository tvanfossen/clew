# Q2 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the index for mutex usage and critical sections in entropic.

### 1. `mcp__doxyguard-db__search`
- **asked:** limit, text
- **got:** {"kind":"matching symbols","count":8,"results":[{"name":"ggml_mutex_lock","kind":"macro definition","file":"extern/llama.cpp/ggml/src/ggml-cpu/ggml-cpu.c","brief":"AcquireSRWLockExclusive(m)","provenance":"ast"},{"name":…

### 2. `mcp__doxyguard-db__search`
- **asked:** limit, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"lock nesting critical section","note":"No matching symbols for 'lock nesting critical section'. This is NOT an error and NOT a malformed call, and it is NOT a …

### 3. `mcp__doxyguard-db__search`
- **asked:** limit, text
- **got:** {"kind":"matching symbols","count":25,"results":[{"name":"mutex","kind":"variable","file":"extern/llama.cpp/ggml/src/ggml-openvino/utils.h"},{"name":"ggml_mutex_destroy","kind":"macro definition","file":"extern/llama.cpp…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, text
- **got:** {"kind":"prose matches","count":10,"results":[{"file_path":"include/entropic/inference/grammar_registry.h","heading":"include/entropic/inference/grammar_registry.h — file-level documentation","snippet":"…safety: - get() …

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"prose matches","count":1,"results":[{"file_path":"include/entropic/inference/adapter_manager.h","heading":"include/entropic/inference/adapter_manager.h — file-level documentation","snippet":"…state) - load/unloa…

### 6. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"lock_nestings","note":"No matching symbols for 'lock_nestings'. This IS a definitive empty result from the database, NOT an error and NOT a malformed call. Do …

### 7. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"kind":"dossiers","count":4,"found":4,"subject":["adapter_mutex_","transition_mutex_","slots_mutex_","tasks_mutex_"],"results":[{"subject":"adapter_mutex_","subject_kind":"lock","lock":{"name":"adapter_mutex_","scope":"…

### 8. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"fire_swap_hook","kind":"function","file":"include/entropic/inference/adapter_manager.h","brief":"Fire ON_ADAPTER_SWAP pre-hook."}],"subject":"fire_swap_hook","targ…

### 9. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject
- **got:** {"subject":"fire_swap_hook","subject_kind":"function","name":"fire_swap_hook","rowid":763,"signature":"bool entropic::AdapterManager::fire_swap_hook(const std::string &current, const std::string &target, const std::files…

### 10. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":3,"results":[{"name":"load_and_activate","kind":"function","file":"include/entropic/inference/backend.h","brief":"Convenience: load() + activate() ."},{"name":"tests/unit/inference/resi…

### 11. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject
- **got:** {"subject":"load_and_activate","subject_kind":"function","name":"load_and_activate","rowid":1384,"signature":"bool entropic::InferenceBackend::load_and_activate(const ModelConfig &config)","file":"include/entropic/infere…

### 12. `mcp__doxyguard-db__search`
- **asked:** limit, text
- **got:** {"kind":"matching symbols","count":15,"results":[{"name":"swap","kind":"function","file":"include/entropic/inference/adapter_manager.h","brief":"Swap to a different adapter atomically."},{"name":"SWAP","kind":"macro defi…

### 13. `mcp__doxyguard-db__dossier`
- **asked:** kind=function
- **got:** {"subject":"swap","subject_kind":"function","name":"swap","rowid":753,"signature":"bool entropic::AdapterManager::swap(const std::string &name, llama_context *ctx)","file":"include/entropic/inference/adapter_manager.h","…

### 14. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"entropic_adapter_swap","subject_kind":"function","name":"entropic_adapter_swap","rowid":52661,"signature":"entropic_error_t entropic_adapter_swap(entropic_handle_t handle, const char *adapter_name)","file":"s…

### 15. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"HandleApiLock","kind":"function","file":"src/facade/engine_handle.h","brief":"Lock handle mutex + enter log scope."},{"name":"entropic::HandleApiLock","kind":"clas…

### 16. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject
- **got:** {"subject":"HandleApiLock","subject_kind":"function","name":"HandleApiLock","rowid":17357,"signature":"entropic::HandleApiLock::HandleApiLock(entropic_handle_t h)","file":"src/facade/engine_handle.h","line_start":175,"li…

### 17. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, text
- **got:** {"kind":"prose matches","count":1,"results":[{"file_path":"include/entropic/inference/adapter_manager.h","heading":"include/entropic/inference/adapter_manager.h — file-level documentation","snippet":"…state) - load/unloa…

### 18. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":4,"results":[{"name":"apply_adapter","kind":"function","file":"src/inference/adapter_manager.cpp","brief":"Apply a single adapter to a context via llama_set_adapters_lora."},{"name":"ap…

### 19. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, qualified, subject
- **got:** {"kind":"dossier","subject":"apply_adapter","found":false,"note":"No dossier for 'apply_adapter' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before concluding th…

### 20. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"identities_mutex_","kind":"variable","file":"include/entropic/core/identity_manager.h","brief":"Guards mutations to identities_ map."},{"name":"include/entropic/co…

### 21. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"identities_mutex_","subject_kind":"lock","lock":{"name":"identities_mutex_","scope":"class:IdentityManager","kind":"shared_mutex","identity_confidence":"high","source":"ast_use","file":"src/core/identity_mana…

### 22. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"registry_mutex_","kind":"variable","file":"include/entropic/inference/grammar_registry.h","brief":"Guards mutations to grammars_ map."},{"name":"include/entropic/i…

### 23. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"registry_mutex_","subject_kind":"lock","lock":{"name":"registry_mutex_","scope":"class:GrammarRegistry","kind":"mutex","identity_confidence":"high","source":"ast_use","file":"src/inference/grammar_registry.cp…

### 24. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, text
- **got:** {"kind":"prose matches","count":6,"results":[{"file_path":"include/entropic/inference/orchestrator.h","heading":"include/entropic/inference/orchestrator.h — file-level documentation","snippet":"include/entropic/inference…

### 25. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"tests/concurrency/test_thread_safety.cpp","heading":"tests/concurrency/test_thread_safety.cpp — file-level documentation","snippet":"…Exercises ToolCallHistory,…

### 26. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"prose matches","count":1,"results":[{"file_path":"docs/roadmap.md","heading":"Issue #4: external_bridge async-task notification deadlocks","snippet":"…Fixed all four contributing causes in this release; v2.2 pro…

### 27. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"auth_mutex_","kind":"variable","file":"include/entropic/mcp/mcp_authorization.h","brief":"Guards mutations to key_sets_ map."},{"name":"include/entropic/mcp/mcp_au…

### 28. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"auth_mutex_","subject_kind":"lock","lock":{"name":"auth_mutex_","scope":"class:MCPAuthorizationManager","kind":"mutex","identity_confidence":"high","source":"ast_use","file":"src/mcp/mcp_authorization.cpp","l…

**Reasoning.** Now let me verify these findings by reading the actual source code at the key points:

### 29. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/secondary_model_loader.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file secondary_model_loader.cpp 4	 * @brief SecondaryModelLoader implementation. 5	 * 6	 * Role-keyed lifecycle for non-primary inference backends. Absorbs the 7	 * li…

### 30. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 2980	 * @return ENTROPIC_OK on success, error code on failure. 2981	 * @internal 2982	 * @version 2.0.0 2983	 */ 2984	entropic_error_t entropic_adapter_swap( 2985	    entropic_handle_t handle, 2986	    const char* adapte…

### 31. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/adapter_manager.cpp
- **got:** 240	 */ 241	bool AdapterManager::swap(const std::string& name, llama_context* ctx) { 242	    std::lock_guard<std::mutex> lock(adapter_mutex_); 243	 244	    auto it = adapters_.find(name); 245	    bool cannot_swap = it ==…

### 32. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/backend.cpp
- **got:** 50	 * @return true on success, false on failure. 51	 * @internal 52	 * @version 2.0.0 53	 */ 54	bool InferenceBackend::load(const ModelConfig& config) { 55	    std::lock_guard<std::mutex> lock(transition_mutex_); 56	 57	…

### 33. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/backend.cpp
- **got:** 88	bool InferenceBackend::activate() { 89	    std::lock_guard<std::mutex> lock(transition_mutex_); 90	 91	    if (state() == ModelState::ACTIVE) { 92	        logger->info("[VRAM] activate() no-op: already ACTIVE"); 93	  …

### 34. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/backend.cpp
- **got:** 160	 * @param config Model config. 161	 * @return true on success. 162	 * @internal 163	 * @version 1.8.2 164	 */ 165	bool InferenceBackend::load_and_activate(const ModelConfig& config) { 166	    if (!load(config)) { 167…

### 35. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":5,"results":[{"name":"api_mutex","kind":"variable","file":"src/facade/engine_handle.h","brief":"Serializes API calls."},{"name":"entropic::HandleApiLock","kind":"class","file":"src/faca…

### 36. `mcp__doxyguard-db__search`
- **asked:** limit, text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"entropic::HandleApiLock","kind":"class","file":"src/facade/engine_handle.h","brief":"gh#59 (v2.3.1): RAII guard combining api_mutex + log scope."}],"subject":"entr…

### 37. `Grep`
- **asked:** pattern=HandleApiLock
- **got:** No files found

### 38. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic && grep -r "HandleApiLock" --include="*.cpp" | head -20
- **got:** src/facade/entropic.cpp:    entropic::HandleApiLock lock(handle);  // gh#59 v2.3.1: mutex + log scope src/facade/entropic.cpp:    entropic::HandleApiLock lock(handle);  // gh#59 v2.3.1: mutex + log scope src/facade/entro…

### 39. `Bash`
- **asked:** command=grep -B5 "HandleApiLock" src/facade/entropic.cpp | grep -E "(bool|void|entropic_error_t|entropic_error_t.*\()" | head -20
- **got:** entropic_error_t entropic_configure_dir( entropic_error_t entropic_validation_resume_retry( entropic_error_t entropic_validation_accept_last( entropic_error_t entropic_context_clear(entropic_handle_t handle) { entropic_e…

### 40. `Bash`
- **asked:** command=grep -n "transition_mutex_" src/inference/backend.cpp | head -10
- **got:** 47: * Acquires transition_mutex_. No-op if already WARM/ACTIVE. 55:    std::lock_guard<std::mutex> lock(transition_mutex_); 89:    std::lock_guard<std::mutex> lock(transition_mutex_); 118:    std::lock_guard<std::mutex> …

### 41. `Bash`
- **asked:** command=grep -n "slots_mutex_" src/inference/secondary_model_loader.cpp
- **got:** 36:    std::lock_guard<std::mutex> lock(slots_mutex_); 68:    std::lock_guard<std::mutex> lock(slots_mutex_); 82:    std::lock_guard<std::mutex> lock(slots_mutex_); 96:    std::lock_guard<std::mutex> lock(slots_mutex_); …

### 42. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, text
- **got:** {"kind":"prose matches","count":4,"results":[{"file_path":"include/entropic/inference/adapter_manager.h","heading":"include/entropic/inference/adapter_manager.h — file-level documentation","snippet":"…LoRA adapter >>life…

### 43. `Bash`
- **asked:** command=grep -r "lock.*order" ~/ddb-targets/entropic/include/ --include="*.h" --include="*.hpp" | head -10
- **got:** (Bash completed with no output)

### 44. `Bash`
- **asked:** command=grep -r "deadlock\|nesting\|reentrant" ~/ddb-targets/entropic/include/ --include="*.h" | head -15
- **got:** ~/ddb-targets/entropic/include/entropic/types/error.h: * entropic API (deadlock risk). Keep callbacks short — log and return. ~/ddb-targets/entropic/include/entropic/core/engine.h:    /// @brief Max delegation nesting de…

### 45. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/inference/adapter_manager.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file adapter_manager.h 4	 * @brief AdapterManager — LoRA adapter lifecycle and hot-swap. 5	 * 6	 * @par Responsibilities 7	 * - Load/unload LoRA adapters against a bas…

### 46. `Bash`
- **asked:** command=grep -rn "transition_mutex_" src/inference/ --include="*.cpp" --include="*.h" | grep -i "secondary\|slot" | head -10
- **got:** (Bash completed with no output)

### 47. `Bash`
- **asked:** command=grep -rn "\.swap(" src/inference/ --include="*.cpp" | head -10
- **got:** src/inference/orchestrator.cpp:1280:        needs_kv_clear = lora_manager_.swap(tier_name, ctx);

### 48. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1270	        return 0.0; 1271	    } 1272	 1273	    const auto& tier_cfg = tier_it->second; 1274	    auto t_start = now(); 1275	    bool needs_kv_clear = false; 1276	 1277	    if (!tier_cfg.adapter_path) { 1278	        ne…

### 49. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1220	    auto it = adapters_.find(tier_name); 1221	    if (it != adapters_.end()) { 1222	        return it->second.get(); 1223	    } 1224	    return nullptr; 1225	} 1226	 1227	// ── LoRA adapter management (v1.9.2) ─────…

### 50. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"ensure_adapter_for_tier","kind":"function","file":"include/entropic/inference/orchestrator.h","brief":"Ensure correct LoRA adapter is active for a tier."}],"subjec…

### 51. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"ensure_adapter_for_tier","subject_kind":"function","name":"ensure_adapter_for_tier","rowid":27109,"signature":"double entropic::ModelOrchestrator::ensure_adapter_for_tier(const std::string &tier_name, llama_c…

### 52. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"ensure_tier_lora","subject_kind":"function","name":"ensure_tier_lora","rowid":27105,"signature":"void entropic::ModelOrchestrator::ensure_tier_lora(const std::string &tier_name, InferenceBackend *result)","fi…

### 53. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1015	 * @return Backend pointer, or nullptr. 1016	 * @internal 1017	 * @version 2.3.7 1018	 */ 1019	InferenceBackend* ModelOrchestrator::get_model(const std::string& tier_name) { 1020	    std::lock_guard<std::mutex> lock…

### 54. `Bash`
- **asked:** command=grep -A20 "bool AdapterManager::load(" src/inference/adapter_manager.cpp | head -30
- **got:** bool AdapterManager::load(     const std::string& name,     const std::filesystem::path& adapter_path,     llama_model* model,     float scale) {     std::lock_guard<std::mutex> lock(adapter_mutex_);      bool preconditi…

### 55. `Bash`
- **asked:** command=grep -n "swap_mutex_" src/inference/orchestrator.cpp | head -20
- **got:** 1020:    std::lock_guard<std::mutex> lock(swap_mutex_); 1716:    std::lock_guard<std::mutex> lock(swap_mutex_); 1732:    std::lock_guard<std::mutex> lock(swap_mutex_); 1803:    std::lock_guard<std::mutex> lock(swap_mutex…

### 56. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/orchestrator.cpp
- **got:** 1710	 * @brief Public footprint accessor — memoizes via tier_footprint_bytes_. 1711	 * @internal 1712	 * @version 2.2.4 1713	 */ 1714	size_t ModelOrchestrator::tier_footprint_bytes( 1715	    const std::string& tier_name)…

**Reasoning.** Now let me search for any locks held together that I might have missed:

### 57. `Bash`
- **asked:** command=grep -n "std::lock_guard\|std::unique_lock\|std::shared_lock" src/facade/entropic.cpp | wc -l
- **got:** 0

### 58. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/facade/engine_handle.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file engine_handle.h 4	 * @brief Private definition of the entropic_engine struct. 5	 * 6	 * The public C API uses `entropic_handle_t` (opaque pointer to 7	 * `struct …

**Reasoning.** ## QUESTION (Q2) ANSWER

Yes, entropic holds two mutexes at once in multiple places, and the acquisition order appears to be **consistent**.

### Confirmed Cases

**Case 1: SecondaryModelLoader → InferenceBackend**

- **Where**: `src/inference/secondary_model_loader.cpp:36-57` in `ensure_loaded()`
- **Locks**: `slots_mutex_` (SecondaryModelLoader) → `transition_mutex_` (InferenceBackend)
- **Code path**: `ensure_loaded()` acquires `slots_mutex_` at line 36, then calls `load_and_activate()` at line 48, which calls `load()` (backend.cpp:55) and `activate()` (backend.cpp:89), both acquiring `tran

---

## Final answer as submitted

## QUESTION (Q2) ANSWER

Yes, entropic holds two mutexes at once in multiple places, and the acquisition order appears to be **consistent**.

### Confirmed Cases

**Case 1: SecondaryModelLoader → InferenceBackend**

- **Where**: `src/inference/secondary_model_loader.cpp:36-57` in `ensure_loaded()`
- **Locks**: `slots_mutex_` (SecondaryModelLoader) → `transition_mutex_` (InferenceBackend)
- **Code path**: `ensure_loaded()` acquires `slots_mutex_` at line 36, then calls `load_and_activate()` at line 48, which calls `load()` (backend.cpp:55) and `activate()` (backend.cpp:89), both acquiring `transition_mutex_`
- **Confidence**: **HIGH** — Clear nested lock acquisition in source code

**Case 2: C API → AdapterManager**

- **Where**: `src/facade/entropic.cpp:2993-3001` in `entropic_adapter_swap()`
- **Locks**: `api_mutex` (EngineHandle) → `adapter_mutex_` (AdapterManager)
- **Code path**: `entropic_adapter_swap()` creates `HandleApiLock lock(handle)` at line 2993 (which acquires `api_mutex` via src/facade/engine_handle.h:176), then calls `swap()` at line 3000 which acquires `adapter_mutex_` at src/inference/adapter_manager.cpp:242
- **Confidence**: **HIGH** — Clear API entry-point pattern with nested internal lock

**Case 3: ModelOrchestrator → AdapterManager**

- **Where**: `src/inference/orchestrator.cpp:1020-1043` in `get_model()`
- **Locks**: `swap_mutex_` (ModelOrchestrator) → `adapter_mutex_` (AdapterManager)
- **Code path**: `get_model()` acquires `swap_mutex_` at line 1020, then calls `ensure_tier_lora()` at line 1043, which calls `ensure_adapter_for_tier()` (line 1280), which calls `swap()` that acquires `adapter_mutex_`
- **Confidence**: **HIGH** — Dossier confirms lock ordering in call chain

### Acquisition Order Consistency

All three cases follow a **consistent hierarchical pattern**:
- **Case 1**: Secondary component → primary backend component
- **Case 2**: API layer → orchestrator's adapter manager  
- **Case 3**: Orchestrator → adapter manager

**No reverse-order acquisitions found.** The architecture prevents circular lock dependencies through layering: higher-level components acquire locks before calling lower-level functions, never the reverse.

## Gaps

- I did not exhaustively verify every code path that touches these mutexes. A complete deadlock analysis would require checking all functions that acquire any of these 7 mutexes (slots_mutex_, transition_mutex_, adapter_mutex_, swap_mutex_, api_mutex, identities_mutex_, registry_mutex_, auth_mutex_, tasks_mutex_) to confirm no other ordering exists.
- The dossier lock nesting information `locks_held` does not surface all transitive lock acquisitions, only direct critical sections; some nested acquisitions required following call chains manually.
