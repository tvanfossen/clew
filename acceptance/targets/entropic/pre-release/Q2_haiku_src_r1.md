# Q2 — src — haiku — run 1

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
