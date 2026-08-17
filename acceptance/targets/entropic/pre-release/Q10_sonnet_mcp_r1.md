# Q10 — mcp — sonnet — run 1

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
