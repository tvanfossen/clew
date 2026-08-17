# Q1 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"locks":[{"name":"mutex","scope":"unknown","kind":"mutex","identity_confidence":"low","source":"ast_use","file":"extern/llama.cpp/ggml/src/ggml-vulkan/ggml-vulkan.cpp","acquisitions":29,"external_root":"extern/llama.cpp…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** kind=class
- **got:** {"subject":"AdapterManager","subject_kind":"class","name":"entropic::AdapterManager","kind":"class","file":"include/entropic/inference/adapter_manager.h","line":58,"brief":"LoRA adapter lifecycle manager.","members":[{"n…

### 3. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossier","subject":"AdapterManager::load","found":false,"note":"No dossier for 'AdapterManager::load' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before…

### 4. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"AdapterManager load adapter_path","note":"No matching symbols for 'AdapterManager load adapter_path'. This is NOT an error and NOT a malformed call, and it is …

### 5. `mcp__doxyguard-db__dossier`
- **asked:** qualified, subject, target
- **got:** {"kind":"dossier","subject":"load","found":false,"note":"No dossier for 'load' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before concluding the symbol does not …

### 6. `Grep`
- **asked:** pattern=adapter_mutex_, path=~/ddb-targets/entropic/src/inference/adapter_manager.cpp
- **got:** Found 1 file ~/ddb-targets/entropic/src/inference/adapter_manager.cpp

### 7. `Grep`
- **asked:** pattern=adapter_mutex_, path=~/ddb-targets/entropic/src/inference/adapter_manager.cpp
- **got:** 79:    std::lock_guard<std::mutex> lock(adapter_mutex_); 126:    std::lock_guard<std::mutex> lock(adapter_mutex_); 165:    std::lock_guard<std::mutex> lock(adapter_mutex_); 209:    std::lock_guard<std::mutex> lock(adapte…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/adapter_manager.cpp
- **got:** 60	 * 61	 * Calls llama_adapter_lora_init() to load the adapter against 62	 * the base model. The adapter stays in RAM until explicitly 63	 * unloaded or the base model is unloaded. 64	 * 65	 * @param name Unique identif…

**Reasoning.** ## Mutexes in entropic

Querying the index's lock inventory (`search corpus=locks`) returns **103 rows over 97 distinct lock identities** (identity = `(name, scope, kind)` at an acquisition site — not 97 physical mutex objects; see confidence discussion below).

**Origin split:** 45 identities belong to this repository (`src/`, `include/`, `tests/`); 52 belong to the vendored `extern/llama.cpp` submodule.

### First-party mutexes (repo-owned, by class)

| Mutex | Owning class | File | Acquisitions |
|---|---|---|---|
| `adapter_mutex_` | `AdapterManager` | `src/inference/adapter_manager.cpp:21

---

## Final answer as submitted

## Mutexes in entropic

Querying the index's lock inventory (`search corpus=locks`) returns **103 rows over 97 distinct lock identities** (identity = `(name, scope, kind)` at an acquisition site — not 97 physical mutex objects; see confidence discussion below).

**Origin split:** 45 identities belong to this repository (`src/`, `include/`, `tests/`); 52 belong to the vendored `extern/llama.cpp` submodule.

### First-party mutexes (repo-owned, by class)

| Mutex | Owning class | File | Acquisitions |
|---|---|---|---|
| `adapter_mutex_` | `AdapterManager` | `src/inference/adapter_manager.cpp:212` | 11 |
| `auth_mutex_` | `MCPAuthorizationManager` | `src/mcp/mcp_authorization.cpp` | 10 |
| `registry_mutex_` | `GrammarRegistry` | `src/inference/grammar_registry.cpp` | 9 |
| `key_mutex_` | `MCPKeySet` | `src/mcp/mcp_key_set.cpp` | 8 |
| `slots_mutex_` | `SecondaryModelLoader` | `src/inference/secondary_model_loader.cpp` | 8 |
| `mu_` | `HandleAwareSink` | `src/types/logging.cpp` | 7 |
| `mutex_` | `ProfileRegistry` | `src/inference/profile_registry.cpp` | 7 |
| `mutex_` | `SqliteDatabase` | `src/storage/database.cpp` | 7 |
| `tasks_mutex_` | `ExternalBridge` | `src/facade/external_bridge.cpp` | 7 (+3 more rows for the same member reached via `bridge.`/`bridge->`/`self->` spellings) |
| `identities_mutex_` (shared_mutex) | `IdentityManager` | `src/core/identity_manager.cpp` | 6 (+4 more via plain-mutex acquisition of the same object) |
| `mutex_` | `PromptCache` | `src/inference/prompt_cache.cpp` | 6 |
| `overrides_mutex_` | `ConstitutionalValidator` | `src/core/constitutional_validator.cpp` | 5 |
| `queue_mutex_` | `AgentEngine` | `src/core/engine.cpp` | 5 |
| `swap_mutex_` | `ModelOrchestrator` | `src/inference/orchestrator.cpp` | 4 |
| `tools_mutex_` | `ExternalMCPClient` | `src/mcp/external_client.cpp` | 4 |
| `transition_mutex_` | `InferenceBackend` | `src/inference/backend.cpp` | 4 |
| `event_mutex_`, `watched_mutex_`, `wake_mutex_` | `HealthMonitor` | `src/mcp/health_monitor.cpp` | 3, 3, 1 |
| `mtp_mutex_`, `seq_id_mutex_` | `LlamaCppBackend` | `src/inference/llama_cpp_backend.cpp` | 3, 2 |
| `mutex_` | `ToolCallHistory` (shared_mutex) | `src/mcp/tool_call_history.cpp` | 3 (+1 plain-mutex row on the same object) |
| `pending_mutex_`, `attempt_boundary_mutex_`, `critique_cbs_mutex_`, `result_mutex_` | `ConstitutionalValidator` | `src/core/constitutional_validator.cpp` | 3, 2, 2, 2 (5 distinct mutex members in one class) |
| `write_mutex_` | `AuditLogger` | `src/storage/audit_logger.cpp` | 3 |
| `s_bound_sockets_mu`, `client_threads_mutex_`, `subscribers_mutex_` | `ExternalBridge` | `src/facade/external_bridge.cpp` / `include/entropic/mcp/external_bridge.h` | 3, 2, 2+1 |
| `delegation_cb_mutex_` | `AgentEngine` | `src/core/engine.cpp` | 2 |
| `mutex_` | `CompactorRegistry` (shared+plain) | `src/core/compactor_registry.cpp` | 2+2 |
| `mutex_` | `ThroughputTracker` | `src/inference/throughput_tracker.cpp` | 2 |
| `mutexes_[idx]` | `HookRegistry` (shared+plain, array) | `src/core/hook_registry.cpp` | 2+2 |
| `pending_mutex_` | `SSETransport` | `src/mcp/transport_sse.cpp` | 2 |
| `s_ggml_log_mu` | file-scope global | `src/inference/inference_c_api.cpp` | 2 |
| `eval_mutex_` | `InferenceBackend` | `src/inference/backend.cpp` | 1 |
| `io_mutex_` | `StdioTransport` | `src/mcp/transport_stdio.cpp` | 1 |
| `write_mutex_` | `PermissionPersister` | `src/storage/permission_persister.cpp` | 1 |

The remaining 52 identities are in the vendored `extern/llama.cpp` tree (e.g. `httplib.cpp`'s `socket_mutex_`, `ggml-vulkan.cpp`'s `queue_mutex`, `server-queue.h`'s `mutex_tasks`) and are not this repo's own concurrency design.

### What executes while `adapter_mutex_` is held

`adapter_mutex_` (11 acquisitions, the highest first-party count) guards `entropic::AdapterManager`'s LoRA adapter table (`src/inference/adapter_manager.cpp:212`, class declared at `include/entropic/inference/adapter_manager.h:212`). Reading its `load()` method (`src/inference/adapter_manager.cpp:73-110`):

```
73  bool AdapterManager::load(...)
78  {
79      std::lock_guard<std::mutex> lock(adapter_mutex_);
81-87      map lookup (adapters_.find) + duplicate/null-model check, early return + error log
89-90      auto* lora = llama_adapter_lora_init(model, adapter_path.c_str());   // <- external llama.cpp call, does GGUF file I/O + parsing
91-95      null check + error log on failure
97-104     build AdapterEntry, adapters_.emplace(name, std::move(entry))
106-108    logger->info(...) success log
110  }   // lock released here (RAII, end of scope)
```

So while `adapter_mutex_` is held, the code runs: a hash-map lookup, a call into `llama_adapter_lora_init` (an external, file-I/O-bound call that loads and parses a `.gguf` adapter file from disk), a map insertion, and two logger calls (error/info paths) — all inside the same lock scope, with no early release before the I/O call. The same pattern (lock at function entry, held for the full body via RAII) repeats at `unload()` (line 126), `activate` (165), `deactivate` (209), `swap` (242), `unload_all_for_model` (295), and others in the same file (lines 344, 371, 387, 402, 418) — 11 lock sites total, matching the index's acquisition count.

### How many distinct mutexes, and confidence

- **Index's raw count: 97 distinct lock *identities*, 45 first-party / 52 vendored.** This is the number the tool reports and it is directly citable.
- **Identity ≠ object**, per the tool's own `row_meaning`: an identity is `(name, scope, kind)`, so one physical `std::mutex`/`std::shared_mutex` accessed via both a `lock_guard` and a `shared_lock` (or via two different expression spellings, e.g. `bridge.tasks_mutex_` vs `bridge->tasks_mutex_` vs `self->tasks_mutex_`) is counted as multiple identities. Collapsing the first-party rows that are clearly the same member reached different ways or under different lock kinds (`tasks_mutex_`/`identities_mutex_`/`mutex_` in `ToolCallHistory`/`CompactorRegistry`/`HookRegistry`/`subscribers_mutex_`), the true count of distinct first-party mutex **objects** is closer to **~39**, not 45.
- 18 of the 97 identities repo-wide are unresolved member expressions (e.g. `bridge->tasks_mutex_`, `tracker->mtx`) that the tool flags as not independently confirmed as distinct objects without further dossier lookups on the owning type.

**My confidence: moderate, not high.** The first-party enumeration (class + file + line) is solid — it comes straight from AST-level lock-use detection with `identity_confidence: high` on all but a handful of pointer-expression rows. But the *headline number* (97, or 45 first-party) systematically overcounts true mutex objects because of the identity-vs-object distinction above, and the tool itself does not resolve that collapse automatically — I did it by hand from the raw rows, so the ~39 figure is my inference, not a directly-reported count.

## Gaps

- The index's symbol-lookup (`dossier`) could not resolve the overloaded method `AdapterManager::load` by name (multiple `load` overloads/ambiguous match); I fell back to `Grep`/`Read` on `src/inference/adapter_manager.cpp` directly to get the lock-held body. This is the documented fallback behavior, not a workaround — the corpus search for `AdapterManager load adapter_path` also came back empty (conjunction search requires every token in one unit).
- I did not independently verify the two-lock nesting pairs the index reports (e.g. `identities_mutex_` → `PromptCache::mutex_` via `store()`/`load_static()`) against source — several of those nestings are flagged `resolved_sites: 0`, meaning the call receiver was never confirmed, so I did not cite them as fact.
- I did not exhaustively re-derive the object-collapse for every one of the 45 first-party rows against source (only inspected `adapter_mutex_` directly); the ~39 estimate for distinct objects is a reasoned collapse from the returned metadata, not a line-by-line re-verification of all 45.
