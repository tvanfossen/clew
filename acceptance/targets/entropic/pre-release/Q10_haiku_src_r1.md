# Q10 — src — haiku — run 1

## Answer

Yes, this codebase implements retry and backoff behavior. Here's where it lives and how it works:

### Primary: Exponential Backoff for MCP Server Reconnection

**ReconnectPolicy** (`src/mcp/reconnect_policy.cpp:54-65` and `include/entropic/mcp/reconnect_policy.h:23-40`) implements exponential backoff with jitter:

```
delay(n) = min(base * factor^n, max) + random_jitter(0, delay*0.1)
```

The formula is computed in `delay_ms()` at `src/mcp/reconnect_policy.cpp:54-65`:
- Line 55-56: `base_delay_ms * pow(backoff_factor, attempt)` — exponential growth
- Line 57: Capped at `max_delay_ms`
- Line 59-64: Adds random jitter (uniform 0-10% of the capped delay)

Default parameters (`include/entropic/types/config.h:50-53`):
- `base_delay_ms = 1000` (1 second initial delay)
- `max_delay_ms = 60000` (60 second maximum)
- `max_retries = 5` (give up after 5 attempts; 0 = infinite)
- `backoff_factor = 2.0` (double the delay each attempt)

### Integration: HealthMonitor

**HealthMonitor** (`src/mcp/health_monitor.cpp` and `include/entropic/mcp/health_monitor.h`) uses `ReconnectPolicy` to orchestrate reconnection:

- **Background thread** (`src/mcp/health_monitor.cpp:137-155`): Runs `monitor_loop()` which polls every 500ms (`src/mcp/health_monitor.cpp:138`)
- **Connection detection** (`src/mcp/health_monitor.cpp:164-179`): Detects when a server disconnects
- **Retry scheduling** (`src/mcp/health_monitor.cpp:204-243`): Calls `policy_.delay_ms(attempt)` at line 236 to compute the next wait time, schedules reconnection at line 238-239
- **Exhaustion check** (`src/mcp/health_monitor.cpp:208`): If `policy_.exhausted(attempt)` returns true, transitions to "error" state and stops retrying (lines 209-219)
- **Success recovery** (`src/mcp/health_monitor.cpp:252-271`): On reconnect success, resets `reconnect_attempt` to 0 (line 256) and refreshes the tool list

### Secondary: Process Termination Retry

**StdioTransport** (`src/mcp/transport_stdio.cpp:518-546`) implements a graceful-then-forceful shutdown pattern:
- Attempts graceful `SIGTERM` and waits up to 3 seconds with 50ms polling (lines 526-539)
- Falls back to `SIGKILL` if the process doesn't terminate (line 542)

### Usage

HealthMonitor is instantiated in `src/mcp/server_manager.cpp` with the reconnect config from the application's MCP configuration, then started when external clients are registered.

## Gaps

- Could not find any retry/backoff behavior for database operations, file I/O, or API calls beyond MCP server reconnection
- No explicit retry loop discovered for transient network failures in tool execution (`src/mcp/tool_executor.cpp` has error handling but no retry delays)
