# Q2 — mcp — haiku — run 1

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
