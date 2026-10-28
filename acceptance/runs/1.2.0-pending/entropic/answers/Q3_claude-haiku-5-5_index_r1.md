The short answer: the decision is made in `ToolExecutor`, and a pattern only matters to `PermissionManager`. The index shows one place where the code contradicts its own header comment, which I describe at the end.

**Decision path for one tool call**

```
model emits call
 └─ ToolExecutor::process_single_call            (tool_executor.cpp:729)
     ├─ PRE_TOOL_CALL hook  → may cancel
     ├─ check_call_preconditions                 (tool_executor.cpp:667)
     │   ├─ anti-spiral hard block
     │   ├─ check_schema
     │   ├─ check_mcp_authorization              (MCP access keys)
     │   ├─ check_tier_allowed                   (tier allowed_tools)
     │   ├─ check_duplicate
     │   └─ check_approval_pc → check_approval   (tool_executor.cpp:161)
     │        approved = auto_approve_tools
     │                || ServerManager::is_explicitly_allowed(allow list)
     │        if !approved && on_tool_call set → approved = true
     │        fire ON_PERMISSION_CHECK (info only)
     ├─ execute_tool → ServerManager::execute    (server_manager.cpp:153)
     │   └─ PermissionManager::is_denied(deny list) → error JSON, tool not run
     │   └─ route_tool_call
     └─ finalize / POST_TOOL_CALL hook
```

So an allow entry only skips prompting. The deny list is enforced later, inside `ServerManager::execute`, so deny still wins even when `auto_approve` is true or the tool is allow-listed.

**What the pattern forms mean**

- Config feeds `PermissionsConfig` (`allow`, `deny`, `auto_approve`) via `parse_permissions_config` (`src/config/loader.cpp:365`). The facade copies `auto_approve` into `loop_config.auto_approve_tools` (`src/facade/entropic.cpp:1489`).
- `ServerManager::execute` and `is_explicitly_allowed` build the match string as `tool_name + ":" + args_to_pattern(args)`. `args_to_pattern` uses the value of the first JSON argument, or `*` if there are none.
- `PermissionManager::pattern_matches` splits the list entry at the first `:`:
  - The part before the colon is an fnmatch glob on the tool name. For example, `filesystem.*` matches every filesystem tool.
  - Without a colon, the tool-name match is enough.
  - With a colon, the whole string must also match the `tool:firstArg` string. For example, `bash.execute:python*` matches `bash.execute` calls whose first argument starts with `python`.
- `is_allowed` and `is_denied` return the first matching entry and log it. The lists are default-deny for allow, and deny takes precedence over allow, as the header states.
- `BashServer::get_permission_pattern` (`src/mcp/servers/bash.cpp:200`) would build `bash.execute:<base-cmd> *`, which is a different string shape from the runtime matcher's. The index shows no runtime caller of it, so I did not confirm where that generated pattern is used.

**Discrepancy to check**

The `PermissionManager` header says tools "must be explicitly allowed or approved via callback." In `check_approval`, though, a non-null `on_tool_call` sets `approved = true` unconditionally after the callback fires. The callback therefore acts as a notification, not a gate. A call with no allow match, no `auto_approve`, and a registered callback still runs unless it is on the deny list. Only with no callback does an unmatched call get refused, with the message "Permission denied." I read this from `src/mcp/tool_executor.cpp:161-186` and did not run it. The docs and the code disagree, and you should decide which one is intended.