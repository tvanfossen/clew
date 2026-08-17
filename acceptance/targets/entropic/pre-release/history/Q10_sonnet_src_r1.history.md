# Q10 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Grep`
- **asked:** pattern=retry|backoff|Retry|Backoff|RETRY|BACKOFF, path=~/ddb-targets/entropic
- **got:** Found 84 files ~/ddb-targets/entropic/src/facade/entropic.cpp ~/ddb-targets/entropic/tests/model/test_gh108_cpu_feasibility.cpp ~/ddb-targets/entropic/tests/model/test_gh108_agentic_benchmark.cpp ~/ddb-targets/entropic/t…

**Reasoning.** Focusing on first-party code (excluding extern/llama.cpp vendor tree): reconnect_policy.cpp/h look like the primary hit.

### 2. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/mcp/reconnect_policy.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file reconnect_policy.h 4	 * @brief Exponential backoff reconnection policy. 5	 * 6	 * Computes delay between reconnection attempts for external MCP 7	 * servers. Thre…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/reconnect_policy.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file reconnect_policy.cpp 4	 * @brief ReconnectPolicy implementation. 5	 * @version 1.8.7 6	 */ 7	 8	#include <entropic/mcp/reconnect_policy.h> 9	 10	#include <algorit…

**Reasoning.** Now let's see where it's used (health_monitor.cpp) and check config defaults.

### 4. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/mcp/health_monitor.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file health_monitor.cpp 4	 * @brief HealthMonitor implementation. 5	 * @version 1.8.7 6	 */ 7	 8	#include <entropic/mcp/health_monitor.h> 9	#include <entropic/types/lo…

### 5. `Grep`
- **asked:** pattern=ReconnectConfig, path=~/ddb-targets/entropic/include/entropic/types/config.h
- **got:** 626:struct ReconnectConfig { 662:    ReconnectConfig reconnect;                   ///< Reconnection backoff policy

### 6. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/types/config.h
- **got:** 600	    bool diagnostics_on_edit = true;   ///< Proactive diagnostics on edit/write 601	    bool fail_on_errors = true;        ///< Rollback edit if it introduces errors 602	    float diagnostics_timeout = 1.0f;  ///< Di…

**Reasoning.** I have enough to give a complete answer. Let me also quickly check the test file for confirmation of expected behavior and check adapter_base.cpp/engine.cpp for any second retry mechanism (inference-side).

### 7. `Grep`
- **asked:** pattern=retry|backoff, path=~/ddb-targets/entropic/src/inference/adapters/adapter_base.cpp
- **got:** Found 1 file ~/ddb-targets/entropic/src/inference/adapters/adapter_base.cpp

### 8. `Grep`
- **asked:** pattern=retry|backoff, path=~/ddb-targets/entropic/src/core/engine.cpp
- **got:** Found 1 file ~/ddb-targets/entropic/src/core/engine.cpp

### 9. `Grep`
- **asked:** pattern=retry|backoff, path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** Found 1 file ~/ddb-targets/entropic/src/facade/entropic.cpp

### 10. `Grep`
- **asked:** pattern=retry|backoff, path=~/ddb-targets/entropic/src/inference/adapters/adapter_base.cpp
- **got:** 219-    // token `<|tool_call|>` decodes through llama.cpp's current pin 220-    // as `<|tool_call>` (trailing `|>` lost). Pre-v2.3.3 the regex 221-    // required a plain `<tool_call>` open, so Gemma 4's actual output …

### 11. `Grep`
- **asked:** pattern=retry|backoff, path=~/ddb-targets/entropic/src/core/engine.cpp
- **got:** 557-    bool made_progress = false; 558-    if (made_tool_call) { 559-        made_progress = process_tool_results(ctx, tool_calls); 560:        // gh#123: reset retry counter so a genuine tool call clears prior 561-    …

### 12. `Grep`
- **asked:** pattern=retry|backoff, path=~/ddb-targets/entropic/src/facade/entropic.cpp
- **got:** 1066-    } 1067-    v["revisions_applied"] = r.revision_count; 1068-    / gh#30 (v2.1.5): structured fields the consumer needs to render 1069:    // a "retry / override / re-prompt" UI without parsing free-form 1070-    …

### 13. `Grep`
- **asked:** pattern=retry|max_consecutive|attempt_n, path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 124:// ── gh#30 (v2.1.5): consumer-driven retry controls ─────── 132:void ConstitutionalValidator::set_auto_retry(bool enabled) { 133:    auto_retry_enabled_.store(enabled); 142:bool ConstitutionalValidator::auto_retry_e…

### 14. `Grep`
- **asked:** pattern=zero_tool_call_retries|max_zero_tool|MAX_RETRIES|retries =, path=~/ddb-targets/entropic/src/core/engine.cpp
- **got:** 559-        made_progress = process_tool_results(ctx, tool_calls); 560-        / gh#123: reset retry counter so a genuine tool call clears prior 561-        // consecutive-empty-turn debt. 562-        if (made_progress) …

### 15. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/core/constitutional_validator.cpp
- **got:** 580	    for (int i = 0; i < config_.max_revisions; ++i) { 581	        const auto& before = result.content; 582	        // gh#30 (v2.1.5): fire attempt-boundary callback before the 583	        // revision so consumers can…

**Reasoning.** I have everything needed for a complete, well-cited answer.

## Answer

Yes — this codebase implements retry/backoff behaviour, and it lives in more than one place, each for a different failure mode:

### 1. Exponential backoff with jitter for MCP server reconnection (the canonical "retry/backoff" implementation)

`ReconnectPolicy` (`include/entropic/mcp/reconnect_policy.h:27`, implemented `src/mcp/reconnect_policy.cpp`) is a dedicated class documented as "Exponential backoff with jitter for reconnection attempts" (`include/entropic/mcp/reconnect_policy.h:21`).

- Formula, as stated in the doc

---

## Final answer as submitted

I have everything needed for a complete, well-cited answer.

## Answer

Yes — this codebase implements retry/backoff behaviour, and it lives in more than one place, each for a different failure mode:

### 1. Exponential backoff with jitter for MCP server reconnection (the canonical "retry/backoff" implementation)

`ReconnectPolicy` (`include/entropic/mcp/reconnect_policy.h:27`, implemented `src/mcp/reconnect_policy.cpp`) is a dedicated class documented as "Exponential backoff with jitter for reconnection attempts" (`include/entropic/mcp/reconnect_policy.h:21`).

- Formula, as stated in the doc comment: `delay(n) = min(base * factor^n, max) + jitter(0, delay*0.1)` (`include/entropic/mcp/reconnect_policy.h:23`).
- `delay_ms(attempt)` computes `base_delay_ms_ * backoff_factor_^attempt`, caps it at `max_delay_ms_`, then adds a uniform random jitter of 0–10% of the capped delay using a `thread_local std::mt19937` RNG (`src/mcp/reconnect_policy.cpp:54-65`).
- `exhausted(attempt)` returns true once `attempt >= max_retries_` (unless `max_retries_ == 0`, meaning infinite retries) (`src/mcp/reconnect_policy.cpp:74-79`).
- Defaults: `base_delay_ms=1000`, `max_delay_ms=60000`, `max_retries=5`, `backoff_factor=2.0` (`include/entropic/mcp/reconnect_policy.h:37-40`, mirrored in `ReconnectConfig` at `include/entropic/types/config.h:626-631`).
- Config is wired into `MCPConfig::reconnect` (`include/entropic/types/config.h:662`), alongside `health_check_interval_ms` (`include/entropic/types/config.h:663`).

**Consumer:** `HealthMonitor` (`src/mcp/health_monitor.cpp`) owns a `ReconnectPolicy policy_` (constructed at `src/mcp/health_monitor.cpp:22-26`) and drives reconnection in `attempt_reconnect()`:
- On each check, if `policy_.exhausted(entry.reconnect_attempt)`, it marks the server `"error"` and stops scheduling further attempts (`src/mcp/health_monitor.cpp:208-219`).
- Otherwise it flips status to `"reconnecting"`, calls `entry.client->connect()`, and on failure computes `policy_.delay_ms(entry.reconnect_attempt)`, increments the attempt counter, and schedules `next_action` that many ms in the future (`src/mcp/health_monitor.cpp:230-243`).
- A background thread (`monitor_loop`, `src/mcp/health_monitor.cpp:137-155`) polls every 500ms and only actually re-attempts connect for servers whose `next_action` deadline has passed (`src/mcp/health_monitor.cpp:140-149`), so the backoff delay is enforced via the `next_action` timestamp rather than a blocking sleep.

This is unit-tested in `tests/unit/mcp/reconnect_policy_test.cpp`.

### 2. A separate, non-backoff retry counter for the agent's "no tool call" failure mode

In the agentic loop (`src/core/engine.cpp`), a per-context `zero_tool_call_retries` counter tracks consecutive model turns that end without a tool call:
- `evaluate_no_tool_decision` reads the counter, compares it to a ceiling (default 3, per-tier overridable via `max_consecutive_empty_turns`), and if under the ceiling appends a `"[SYSTEM] ... Retry."` correction message and increments the counter (`src/core/engine.cpp:772-816`).
- A genuine tool call resets the counter to `"0"` (`src/core/engine.cpp:558-564`).
- This is a fixed-count retry-with-correction-message scheme, not a timed backoff — there's no delay computation here, just a retry cap and a corrective prompt.

Separately, `push_delegation_cycle_rejected`/`is_delegation_repeat_blocked` refuse to keep re-delegating to a target that has just failed `max_consecutive_failed_delegations` times in a row (`src/core/engine.cpp:2112-2162`, gh#64) — again a retry-limiting/circuit-breaker mechanism, not a timed backoff.

### 3. Constitutional-validator revision retries

`ConstitutionalValidator` (`src/core/constitutional_validator.cpp`) loops up to `config_.max_revisions` times attempting a compliant revision (`src/core/constitutional_validator.cpp:580-624`), tracking `attempt_n`, and exposes consumer-driven controls `set_auto_retry`/`auto_retry_enabled`/`resume_retry` (gh#30) so a caller can pause and resume the retry loop (`src/core/constitutional_validator.cpp:124-157`). This, too, is attempt-count-based with no delay/backoff component.

### Summary

Only the MCP external-server reconnection path (`ReconnectPolicy` + `HealthMonitor`) implements true exponential backoff with jitter and a delay schedule. The engine's tool-call retry and delegation-repeat guard, and the constitutional validator's revision loop, are retry-*count* mechanisms (bounded attempts + corrective messaging) with no time-based backoff.

## Gaps

- I excluded `extern/llama.cpp/` (vendored third-party submodule) from this answer per the question's framing of "this codebase" — that tree has its own retry/backoff logic (e.g. `common/download.cpp`, `ggml-rpc/transport.cpp`) but it is not first-party entropic code.
- I did not trace every caller of `HealthMonitor`/`ReconnectPolicy` to confirm exhaustive coverage of all external MCP server types beyond what's visible in `health_monitor.cpp`; that file appears complete for this purpose.
- `tasks.py` and `RELEASE_NOTES.md`/`docs/roadmap.md` matched the grep but were not examined — they are non-source (build/docs) and unlikely to add another implementation.
