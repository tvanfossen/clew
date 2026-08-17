# Q10 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":17,"results":[{"name":"auto_retry_enabled","kind":"function","file":"include/entropic/core/constitutional_validator.h","brief":"Whether auto-revision is currently enabled."},{"name":"en…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":7,"results":[{"name":"backoff_factor","kind":"variable","file":"include/entropic/types/config.h","brief":"Exponential backoff multiplier."},{"name":"backoff_factor_","kind":"variable","…

**Reasoning.** Found it — `entropic::ReconnectPolicy` is the real backoff mechanism. Let me get the full dossier.

### 3. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":2,"found":1,"subject":["entropic::ReconnectPolicy","health_monitor.h"],"results":[{"subject":"entropic::ReconnectPolicy","subject_kind":"class","name":"entropic::ReconnectPolicy","kind":"class"…

### 4. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/mcp/reconnect_policy.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file reconnect_policy.h 4	 * @brief Exponential backoff reconnection policy. 5	 * 6	 * Computes delay between reconnection attempts for external MCP 7	 * servers. Thre…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["entropic::HealthMonitor","entropic::ReconnectConfig"],"results":[{"subject":"entropic::HealthMonitor","subject_kind":"class","name":"entropic::HealthMonitor","kind":"cla…

### 6. `Bash`
- **asked:** command=find ~/ddb-targets/entropic/src -iname "reconnect_policy*" -o -iname "health_monitor*"
- **got:** ~/ddb-targets/entropic/src/mcp/health_monitor.cpp ~/ddb-targets/entropic/src/mcp/reconnect_policy.cpp

### 7. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/reconnect_policy.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file reconnect_policy.cpp 4	 * @brief ReconnectPolicy implementation. 5	 * @version 1.8.7 6	 */ 7	 8	#include <entropic/mcp/reconnect_policy.h> 9	 10	#include <algorit…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/health_monitor.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file health_monitor.cpp 4	 * @brief HealthMonitor implementation. 5	 * @version 1.8.7 6	 */ 7	 8	#include <entropic/mcp/health_monitor.h> 9	#include <entropic/types/lo…

### 9. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossier","subject":"\"entropic::ConstitutionalValidator\"","found":false,"note":"No dossier for '\"entropic::ConstitutionalValidator\"' in this index. This is a definitive negative from the database, NOT an erro…

### 10. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"entropic::ConstitutionalValidator","subject_kind":"class","name":"entropic::ConstitutionalValidator","kind":"class","file":"include/entropic/core/constitutional_validator.h","line":82,"brief":"Post-generation…

### 11. `Grep`
- **asked:** pattern=max_revision_attempts|revision_attempts|max_attempts, path=~/ddb-targets/entropic/include/entropic/core/constitutional_validator.h
- **got:** No matches found

### 12. `Bash`
- **asked:** command=grep -n "max_revision_attempts\|revision_attempts\|max_attempts" ~/ddb-targets/entropic/src/core/constitutional_validator.cpp 2>/dev/null | head -30
- **got:** (Bash completed with no output)

### 13. `Bash`
- **asked:** command=find ~/ddb-targets/entropic/src -iname "constitutional_validator*"
- **got:** ~/ddb-targets/entropic/src/core/constitutional_validator.cpp

### 14. `Grep`
- **asked:** pattern=apply_revisions|max_revisions|attempt|while|for \(, path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 107:    for (const auto& skip : config_.skip_tiers) { 149: * Pops the cached pending state, runs `apply_revisions()` against it 167:    auto result = apply_revisions( 178: * @brief Finalize the paused attempt as the cons…

**Reasoning.** Good, confirms bound `config_.max_revisions` at line 580. Now I have enough for both mechanisms.

### 15. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 575	ValidationResult ConstitutionalValidator::apply_revisions( 576	    ValidationResult result, 577	    const CritiqueResult& initial_critique, 578	    const char* messages_json) { 579	    auto critique = initial_critiqu…

**Reasoning.** Now I have everything needed to answer.

## Answer

Yes — two distinct retry/backoff mechanisms exist, serving different purposes.

**1. Exponential backoff with jitter for MCP server reconnection** — the canonical "retry/backoff" implementation.

- `entropic::ReconnectPolicy` (`include/entropic/mcp/reconnect_policy.h:27`) implements `delay(n) = min(base * factor^n, max) + jitter(0, delay*0.1)` (doc comment at `include/entropic/mcp/reconnect_policy.h:23`).
- Implementation in `src/mcp/reconnect_policy.cpp:54-65` (`delay_ms`): computes `base_delay_ms_ * backoff_factor_^attempt`, caps at `max_de

---

## Final answer as submitted

Now I have everything needed to answer.

## Answer

Yes — two distinct retry/backoff mechanisms exist, serving different purposes.

**1. Exponential backoff with jitter for MCP server reconnection** — the canonical "retry/backoff" implementation.

- `entropic::ReconnectPolicy` (`include/entropic/mcp/reconnect_policy.h:27`) implements `delay(n) = min(base * factor^n, max) + jitter(0, delay*0.1)` (doc comment at `include/entropic/mcp/reconnect_policy.h:23`).
- Implementation in `src/mcp/reconnect_policy.cpp:54-65` (`delay_ms`): computes `base_delay_ms_ * backoff_factor_^attempt`, caps at `max_delay_ms_`, then adds uniform random jitter in `[0, 10% of delay]` using a `thread_local std::mt19937`.
- `exhausted()` (`src/mcp/reconnect_policy.cpp:74-79`) returns true once `attempt >= max_retries_` (`max_retries_ == 0` means infinite retries).
- Defaults: `base_delay_ms=1000, max_delay_ms=60000, max_retries=5, backoff_factor=2.0` (`include/entropic/mcp/reconnect_policy.h:37-40`), overridable via `entropic::ReconnectConfig` (`include/entropic/types/config.h:626-630`).
- Driven by `entropic::HealthMonitor` (`include/entropic/mcp/health_monitor.h:55`), which runs a background thread (`monitor_thread_`, `src/mcp/health_monitor.cpp:92-93`) polling every 500ms (`src/mcp/health_monitor.cpp:138`). On connection loss it calls `attempt_reconnect()` (`src/mcp/health_monitor.cpp:204-243`):
  - checks `policy_.exhausted(entry.reconnect_attempt)` and gives up into an `"error"` state if so (`src/mcp/health_monitor.cpp:208-219`);
  - otherwise tries `entry.client->connect()`, and on failure schedules the next attempt at `now + policy_.delay_ms(entry.reconnect_attempt)`, incrementing `reconnect_attempt` (`src/mcp/health_monitor.cpp:236-239`).
  - `on_reconnect_success()` (`src/mcp/health_monitor.cpp:252-271`) resets the attempt counter to 0 and refreshes the client's tool list.

**2. A separate, non-timed retry loop for constitutional validation** ("revise-and-recheck", not backed off by delay).

- `entropic::ConstitutionalValidator::apply_revisions()` (`src/core/constitutional_validator.cpp:575-630`) loops up to `config_.max_revisions` times (`src/core/constitutional_validator.cpp:580`): each iteration calls `attempt_revision()`, re-runs `run_critique()`, and breaks early if `critique.compliant` (`src/core/constitutional_validator.cpp:623`).
- No delay/backoff between attempts — it's an immediate bounded retry with a length safety valve (rejects a revision that shrinks content by >50%, `src/core/constitutional_validator.cpp:602-613`) and a terminal `rejected_max_revisions` verdict when the loop is exhausted (`src/core/constitutional_validator.cpp:626-630`).
- Separately gated by `auto_retry_enabled_`/`set_auto_retry()`/`resume_retry()` (`include/entropic/core/constitutional_validator.h:198-219`), which controls whether this revision pass runs automatically after a rejection at all, plus a "reject-retry loop" test fixture referencing this behavior at `tests/unit/core/engine_test.cpp` (per search hit).

## Gaps

- I did not trace every call site of `HealthMonitor::watch()`/where `ReconnectPolicy` gets constructed with non-default config (e.g. from user-facing config parsing) — only confirmed the struct/class definitions and their direct implementation files.
- `connect_bridge_client` (`tests/unit/api/entropic_capi_test.cpp`, "bounded retry") is test-only scaffolding and not examined in detail since it's not production retry logic.
- Did not check whether other subsystems (e.g. inference API calls, tool execution) implement additional ad hoc retry logic beyond these two; the index search for "retry"/"backoff" surfaced only these as structural mechanisms, but a broader sweep (e.g. searching "attempt" alone) wasn't performed.
