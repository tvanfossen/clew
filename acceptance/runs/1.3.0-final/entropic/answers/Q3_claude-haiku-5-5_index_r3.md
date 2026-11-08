**Short answer:** The allow and deny lists are checked in two different places. The allow list only decides whether the user is prompted. The deny list is enforced later, inside the dispatcher. And in the current code, a call that isn't allow-listed is approved anyway whenever a frontend callback is wired, so the prompt is a notification, not a gate.

### Flow

```
model emits tool call
  └─ ToolExecutor::check_call_preconditions           src/mcp/tool_executor.cpp:667
       1. anti-spiral hard block
       2. check_schema (argument validation)
       3. check_mcp_authorization                      (not inspected)
       4. check_tier_allowed (tier allowed_tools)
       5. check_duplicate
       6. check_approval_pc → check_approval           :161
            a. auto_ok = auto_approve_tools || ServerManager::is_explicitly_allowed (allow list)
            b. if !auto_ok and on_tool_call set → call the callback, approved = true
            c. if !auto_ok and no callback → denied ("headless")
  └─ execute_tool → ServerManager::execute            src/mcp/server_manager.cpp:153
       d. is_denied(tool, "tool:args") → return "Error: Permission denied" JSON
       e. route_tool_call → the MCP server runs
```

### What each list does

Both lists hold `PermissionManager` patterns (`include/entropic/mcp/permission_manager.h`, `src/mcp/permission_manager.cpp`):

- **Bare pattern, e.g. `filesystem.*`**: `fnmatch`s against the fully-qualified tool name only. Matches every call to that tool, whatever its arguments.
- **Pattern with a colon, e.g. `bash.execute:python*`**: the part before the first colon must match the tool name. The full pattern must also match the string `tool:args`, built by `args_to_pattern`. The argument format wasn't read, so the example's intent is taken from the header comment.
- **Allow list**: consulted only in step 6a. A match skips the prompt. It does not run anything by itself.
- **Deny list**: consulted only in step d, after approval has already happened. A match returns an error result and the tool never runs. A pattern in both lists still gets denied, because step d always runs.
- **`auto_approve_tools`** (`config.permissions.auto_approve`, wired at `src/facade/entropic.cpp:1489`) skips the allow-list check but not the deny check.

### Things the code shows that you may not expect

1. **The callback doesn't deny.** `on_tool_call` returns `void`, so when it is wired, `check_approval` sets `approved = true` after notifying it. The only real denial in the approval step is the headless case (no callback, not allowed). Anything not on the deny list therefore runs once a frontend is attached.
2. **Deny is enforced after approval.** Step d runs inside `ServerManager::execute`, which is downstream of `check_approval`. So a denied call still reaches the approval hook and is reported as approved to `ON_PERMISSION_CHECK` observers, then blocked.
3. **"Always allow/deny" persistence is not wired.** `set_permission_persist` has no callers, and nothing in `src/` invokes `permission_persist_`. The `PermissionPersister` exists but nothing calls `save_permission`. The `ALWAYS_ALLOW`/`ALWAYS_DENY` response path described in `engine_types.h:561` has no implementation in `src/`, so no pattern is saved across sessions.
4. **`get_permission_pattern` is off the gating path.** Its only callers are the destructor and tests. Gating uses `args_to_pattern` through `is_explicitly_allowed`/`is_denied`, so per-server overrides such as `BashServer::get_permission_pattern` don't affect the decision.

Where the lists come from: `permissions.allow` / `permissions.deny` / `permissions.auto_approve` are parsed in `src/config/loader.cpp:365` and passed to `ServerManager`'s constructor, which builds the `PermissionManager` (`src/mcp/server_manager.cpp:35`).

If you want a hard prompt gate, `on_tool_call` would need a return value (or a blocking response path) that `check_approval` honours. As written, that gate doesn't exist.