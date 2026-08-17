# Q10 — src — sonnet — run 1

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
