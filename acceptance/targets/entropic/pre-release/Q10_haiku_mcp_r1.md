# Q10 — mcp — haiku — run 1

---

## Answer

Yes, this codebase implements **two distinct retry/backoff mechanisms**:

### 1. **MCP Server Reconnection with Exponential Backoff**

**Location:** `include/entropic/mcp/reconnect_policy.h` (class definition), `src/mcp/reconnect_policy.cpp` (implementation)

**How it works:**

The `ReconnectPolicy` class implements exponential backoff with jitter for reconnecting to external MCP servers:

- **Configuration** (`include/entropic/types/config.h:627-630`):
  - `base_delay_ms = 1000`: Initial retry delay (1 second)
  - `max_delay_ms = 60000`: Maximum delay cap (60 seconds)
  - `backoff_factor = 2.0`: Exponential multiplier
  - `max_retries = 5`: Maximum reconnection attempts

- **Delay calculation** (`src/mcp/reconnect_policy.cpp:54-65`): 
  - Computes exponential backoff: `delay = base_delay_ms × backoff_factor^attempt`
  - Caps at `max_delay_ms`
  - **Adds jitter**: uniform random value in range [0, 10% of delay] to avoid thundering herd

- **Integration with HealthMonitor** (`include/entropic/mcp/health_monitor.h`):
  - `HealthMonitor` monitors external server connections in a background thread
  - On connection loss, `attempt_reconnect()` (`src/mcp/health_monitor.cpp:204-243`) uses the policy to schedule reconnection attempts
  - Checks `policy_.exhausted()` to stop after max retries exceeded
  - Logs reconnection state transitions and delays

### 2. **Constitutional Validation Retry Loop**

**Location:** `include/entropic/core/constitutional_validator.h`

**How it works:**

The validator implements optional automatic revision retry after rejection:

- **Control mechanism** (`include/entropic/core/constitutional_validator.h:132-144`):
  - `set_auto_retry(bool)`: Enable/disable automatic revision on critique failure (default: true)
  - `auto_retry_enabled()`: Query current state

- **Behavior**:
  - When `validate()` encounters a critique failure and `auto_retry_enabled_` is false, it returns with verdict `paused_pending_consumer` and caches validation state
  - When true, it automatically enters revision loop (calls `apply_revisions()` repeatedly)
  - `resume_retry()` (`src/core/constitutional_validator.cpp:157-175`) allows manual resumption of a paused revision loop

Note: The constitutional validator uses **bounded iteration** (controlled by `auto_retry_enabled_` flag) rather than a time-based backoff like the MCP reconnection policy.

---

## Gaps

None — the index provided comprehensive coverage of both retry mechanisms with complete implementation details visible.
