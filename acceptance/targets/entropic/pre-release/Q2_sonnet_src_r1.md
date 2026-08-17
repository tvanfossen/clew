# Q2 — src — sonnet — run 1

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
