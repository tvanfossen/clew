**Short answer:** the call runs only if it clears a fixed sequence of checks in `ToolExecutor`. The permission lists are consulted at two points in that sequence, and the deny list is enforced at the second one, not the first.

## Order of decision

```
model emits ToolCall
  │
  ▼ ToolExecutor::process_single_call
  1. PRE_TOOL_CALL hook ── can cancel ("Cancelled by hook")
  │
  ▼ check_call_preconditions (first failure wins)
  2. anti-spiral hard block      (consecutive same-tool count)
  3. schema check
  4. MCP key authorization       check_mcp_authorization → access level
  5. tier allowed_tools          check_tier_allowed
  6. duplicate-call check
  7. approval                    check_approval_pc → check_approval
  │
  ▼ execute_tool
  8. ServerManager::execute
       is_denied(tool, "tool:argpattern") ── yes → "Error: Permission denied"
       else route_tool_call
```

Steps 2–6 are not governed by the lists, so an allow entry cannot bypass the tier or MCP-key checks.

**Step 7, `check_approval`:**
- Auto-approved if `LoopConfig.auto_approve_tools` is true, or if `ServerManager::is_explicitly_allowed` finds a match in the allow list.
- Otherwise, if an `on_tool_call` callback is registered, it is invoked and `approved` is set to `true` unconditionally. Its return type is void, so it cannot say no.
- With no callback, the call is denied ("No approval callback — denying").

**Step 8, `ServerManager::execute`:** this is the only place `is_denied` runs. A matching deny pattern returns a `Permission denied` result without dispatching. Because `check_approval` runs first, a call can be prompted or allowed, then blocked here.

## What a pattern means

Patterns are strings matched with `fnmatch` (flags 0, so `*` also crosses `/`). Each has the form `tool` or `tool:argpattern`.

- **`tool` with no colon** (`filesystem.read_file`): matches the tool name only, for any arguments. `filesystem.*` matches every tool in that server.
- **`tool:argpattern`** (`filesystem.read_file:/etc/*`): the tool part must match, then the full `tool:argvalue` string must match.
- **The argvalue** comes from `args_to_pattern`. It is the value of the first key of the arguments object, or `*` if the arguments are empty or unparseable. Nlohmann objects iterate in key order, so "first" is alphabetically first key, not the first argument written. I did not verify this at runtime.
- **Bash override:** `BashServer::get_permission_pattern` builds `bash.execute:<base_cmd> *`. So `bash.execute:git *` matches `git status` and `git log`. The base command is the text before the first space.
- **Persistence:** "Always Allow/Deny" writes the pattern into `permissions.allow` or `permissions.deny` in the project YAML through `PermissionPersister` (read-modify-write).

## Things that look wrong

1. **The approval callback never denies.** The header says tools are "approved via callback", but `check_approval` sets `approved = true` after calling the callback. As indexed, a registered callback is a notification, not a gate.
2. **The header's "deny takes precedence" is true only at step 8.** A denied tool that matches an allow entry is still approved at step 7, so the user may be prompted for a call that will be blocked anyway.
3. **`permissions.auto_approve` may not reach the loop.** `PermissionsConfig.auto_approve` is parsed by `parse_permissions_config`, but the index shows no site that copies it into `LoopConfig.auto_approve_tools`. I could not confirm the wiring from the index; check it by reading the config-to-engine code.