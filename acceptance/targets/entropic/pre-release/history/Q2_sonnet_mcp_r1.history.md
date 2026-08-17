# Q2 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"locks":[{"name":"mutex","scope":"unknown","kind":"mutex","identity_confidence":"low","source":"ast_use","file":"extern/llama.cpp/ggml/src/ggml-vulkan/ggml-vulkan.cpp","acquisitions":29,"external_root":"extern/llama.cpp…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** qualified, subject
- **got:** {"kind":"dossiers","count":6,"found":6,"subject":["cleanup_expired_tasks","load_static","load","check_access","record","store"],"results":[{"subject":"cleanup_expired_tasks","subject_kind":"function","name":"cleanup_expi…

### 3. `Bash`
- **asked:** command=sed -n '50,80p' ~/ddb-targets/entropic/src/inference/backend.cpp; echo ---; sed -n '20,50p' ~/ddb-targets/entropic/src/inference/throughput_tracker.cpp
- **got:** * @return true on success, false on failure.  * @internal  * @version 2.0.0  */ bool InferenceBackend::load(const ModelConfig& config) {     std::lock_guard<std::mutex> lock(transition_mutex_);      if (state() != ModelS…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["has_access","MCPKeySet"],"results":[{"subject":"has_access","subject_kind":"function","name":"has_access","rowid":25888,"signature":"bool entropic::MCPKeySet::has_access…

### 5. `Bash`
- **asked:** command=sed -n '985,997p' ~/ddb-targets/entropic/extern/llama.cpp/tools/server/server-models.cpp
- **got:** });          // we reach here when the child process exits (stdout EOF)         // note: we cannot join() prior to this point because it will close stdin_file         if (log_thread.joinable()) {             log_thread.j…

### 6. `Grep`
- **asked:** pattern=scoped_lock|lock\(.*,.*\), path=~/ddb-targets/entropic/src
- **got:** Found 1 file ~/ddb-targets/entropic/src/mcp/tool_executor.cpp

### 7. `Grep`
- **asked:** pattern=scoped_lock|lock\(.*,.*\), path=~/ddb-targets/entropic/src/mcp/tool_executor.cpp
- **got:** Found 1 file ~/ddb-targets/entropic/src/mcp/tool_executor.cpp

### 8. `Grep`
- **asked:** pattern=scoped_lock, path=~/ddb-targets/entropic/src/mcp/tool_executor.cpp
- **got:** No matches found

### 9. `Grep`
- **asked:** pattern=lock\(.*,.*\), path=~/ddb-targets/entropic/src/mcp/tool_executor.cpp
- **got:** 673:    PreconditionCheck pc = check_anti_spiral_hard_block(ctx, call);

**Reasoning.** ## Answer

**Yes — entropic holds two mutexes at once in exactly one confirmed first-party case, and its acquisition order is consistent (single order, no reversal found). Several other index-reported "nestings" turned out to be false positives from name-collision, which is itself worth reporting.**

### Confirmed real case: `auth_mutex_` (outer) → `key_mutex_` (inner)

`MCPAuthorizationManager::check_access` takes its own `auth_mutex_`, then calls `MCPKeySet::has_access` on an entry found in its map — and `has_access` takes `MCPKeySet`'s own `key_mutex_` while `auth_mutex_` is still held:

- 

---

## Final answer as submitted

## Answer

**Yes — entropic holds two mutexes at once in exactly one confirmed first-party case, and its acquisition order is consistent (single order, no reversal found). Several other index-reported "nestings" turned out to be false positives from name-collision, which is itself worth reporting.**

### Confirmed real case: `auth_mutex_` (outer) → `key_mutex_` (inner)

`MCPAuthorizationManager::check_access` takes its own `auth_mutex_`, then calls `MCPKeySet::has_access` on an entry found in its map — and `has_access` takes `MCPKeySet`'s own `key_mutex_` while `auth_mutex_` is still held:

- `src/mcp/mcp_authorization.cpp:98` — `std::lock_guard<std::mutex> lock(auth_mutex_);` in `check_access`
- `src/mcp/mcp_authorization.cpp:105` — `it->second.has_access(tool_name, required_level)` called while `auth_mutex_` is held
- `src/mcp/mcp_key_set.cpp:60` — `std::lock_guard<std::mutex> lock(key_mutex_);` inside `has_access` (i.e. `key_mutex_` acquired while `auth_mutex_` is still live)
- Second site, same order: `src/mcp/mcp_authorization.cpp:128-145` (`grant_from`) also calls `has_access` (line 135) while holding `auth_mutex_`.

Both call sites (`check_access`, `grant_from`) take `auth_mutex_` before `key_mutex_`; nothing in `MCPKeySet`'s own methods (`grant`, `revoke`, `has_access`, `list`, `size`, `clear`, `serialize`, `deserialize` — `include/entropic/mcp/mcp_key_set.h:55-144`) ever calls back into `MCPAuthorizationManager`, so `key_mutex_` → `auth_mutex_` in the reverse order does not occur.

**Confidence: high.** Verified by reading both function bodies directly (not just the index's inferred edge), and the index reports this call resolution as `resolved_sites` positive (the `has_access` call target is a `MCPKeySet` member reached through a type-known map entry).

### Index-reported nestings that are false positives (worth flagging)

The index's `lock_nestings` query surfaced four more apparent first-party two-mutex holdings, all keyed on the callee name `store` or `remove`:

- `identities_mutex_` (`IdentityManager`) → `mutex_` (`PromptCache`) — reported via a `store` call at `src/core/identity_manager.cpp:181`. Reading the line: `router_dirty_.store(true, std::memory_order_release);` — this is `std::atomic<bool>::store`, not `PromptCache::store`. **False positive.**
- `transition_mutex_` (`InferenceBackend`) → `mutex_` (`PromptCache`) — reported via `src/inference/backend.cpp:76`. That line is `state_.store(ModelState::WARM, std::memory_order_release);` — again an atomic store. **False positive.**
- `mutex_` (`ThroughputTracker`) → `mutex_` (`PromptCache`) — reported via `src/inference/throughput_tracker.cpp:37`. That line is `ewma_tok_s_.store(...)` — atomic store. **False positive.**
- `tasks_mutex_` (`ExternalBridge`) → `mutex` (`server_models`, vendored) — reported via a `remove` call at `src/facade/external_bridge.cpp:1360`. That line is `std::filesystem::remove(sentinel_dir / (it->first + suffix), ec);` — unrelated to `server_models`. **False positive.**

All four are flagged `resolution: "receiver_unverified"` / `resolved_sites: 0` in the raw data, which is exactly the signal that should have stopped me from reporting them as real without checking source — the index correctly declined to claim confidence, and reading the cited lines confirmed they're spurious matches on a common method name (`store`, `remove`) rather than genuine nested locking.

### Vendored code (not entropic's own, out of scope but present in the tree)

`extern/llama.cpp` contains its own two-mutex holdings (e.g. `ping_mutex_`→`write_mutex_` in `WebSocket`, `extern/llama.cpp/vendor/cpp-httplib/httplib.cpp:16429`, and `device->mutex`→`queue_mutex` in the Vulkan backend, `extern/llama.cpp/ggml/src/ggml-vulkan/ggml-vulkan.cpp:7954` and `:8065`, both in the same order). These are upstream/vendored, not written by entropic, so I've excluded them from the "does entropic hold two mutexes" verdict above — call them out only if you want vendored code in scope.

## Gaps

- I did not exhaustively audit every one of entropic's 45 first-party lock identities for two-mutex holdings beyond what `lock_nestings` surfaced — I relied on the index's nesting detector plus manual verification of every first-party hit it returned. If a nested acquisition exists that doesn't route through a call the index's AST layer resolved (e.g. two `lock_guard`s in the same function with no call in between), it would not appear as a "nesting" edge in this query and I did not separately grep for that pattern beyond a `scoped_lock`/multi-arg-`lock(` sweep of `src/`, which found nothing.
- I did not check whether any first-party function takes a lock, calls into vendored `extern/llama.cpp` code, and that vendored code re-enters entropic's own locks (a cross-boundary cycle) — the index's `nestings` results didn't surface one, but cross-repo call resolution is a known weak spot for AST-only edges.
