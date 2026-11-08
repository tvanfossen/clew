**Short answer:** the deny list is the only check that can block a call once it reaches dispatch. The allow list only skips a prompt. Whether an unlisted call runs depends on whether an `on_tool_call` callback is registered. Several other gates run before permissions are consulted.

## Order of checks

```
model emits tool call
 └─ ToolExecutor::process_single_call          src/mcp/tool_executor.cpp:729
    1. PRE_TOOL_CALL hook             → may cancel ("Cancelled by hook")
    2. check_call_preconditions       :667
       a. anti-spiral hard block
       b. check_schema                 (JSON-schema args)
       c. check_mcp_authorization
       d. check_tier_allowed           (tier allowed_tools, gh#83)  ← not bypassed by auto_approve
       e. duplicate-call check
       f. check_approval_pc → check_approval   :161
          • auto_approve_tools → approved
          • else is_explicitly_allowed (allow list) → approved
          • else if on_tool_call callback set → approved = true (notify only)
          • else → "Permission denied"
    3. execute_tool → ServerManager::execute      server_manager.cpp:153
          • is_denied(deny list) → "Error: Permission denied for <tool>"
          • else route_tool_call
```

Step 3 is the real deny gate. It runs after approval, so a deny match still blocks a call that was auto-approved or callback-approved.

## What a pattern means

Patterns are stored as `tool` or `tool:arg`, matched with `fnmatch` (`permission_manager.cpp:101`):

- **No colon** (`filesystem.*`): matches the tool name only. `*` covers every tool in that server.
- **With colon** (`bash.execute:python*`): the tool portion must match, then the whole string is matched against `tool:<arg>`.
- **The arg** comes from `ServerManager::args_to_pattern` (`server_manager.cpp:426`). It is the first member's value if that value is a string. Empty or `{}` args give `*`. Only the first argument is ever compared.
- No `FNM_PATHNAME`, so `*` also matches `/`.
- Deny and allow use the same matcher. Deny is checked in `ServerManager::execute`, and `is_denied` runs first there.

Config comes from `permissions.allow`, `permissions.deny` and `permissions.auto_approve` (`src/config/loader.cpp:365`). The `PermissionManager` is built from the allow and deny lists (`server_manager.cpp:35`). "Always allow/deny" choices are written back to the YAML by `PermissionPersister`.

## Problems I found

1. **The callback never denies.** When `on_tool_call` is set, `check_approval` sets `approved = true` after calling it. The return value is never read. The header says tools "must be explicitly allowed or approved via callback", but in the code the callback only notifies. Default-deny holds only when no callback is registered.
2. **The ON_PERMISSION_CHECK hook can say "allowed" for a call that is then denied.** It fires inside `check_approval`, before the deny-list check in `ServerManager::execute`.
3. **"Always allow" patterns may not match the call they came from.** Bash's `get_permission_pattern` (`bash.cpp:213`) produces `bash.execute:<base> *` with a literal space. Matching uses the raw first argument, and `is_explicitly_allowed` does not call `get_permission_pattern`. So a bare `ls` would produce `bash.execute:ls *` and then fail to match itself. I reasoned this from the code and have not run it. Also, nothing under `src/` calls `ServerManager::get_permission_pattern`, so I could not find where the "Always allow" pattern is generated.

Tests for the matcher are in `tests/unit/mcp/permission_manager_test.cpp`. I did not run them.