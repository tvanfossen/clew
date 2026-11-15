The decision runs in two places: an approval check before dispatch, then a deny check at execution. The deny check is the only one that can stop a call once the approval check has passed.

```
tool call
  │
  ▼
ToolExecutor::check_call_preconditions          (tool_executor.cpp:667)
  1. anti-spiral hard block
  2. check_schema
  3. check_mcp_authorization   (MCP key access level)
  4. check_tier_allowed
  5. check_duplicate
  6. check_approval_pc → check_approval
        ├─ auto_approve_tools? ─────────────────────► approved
        ├─ ServerManager::is_explicitly_allowed
        │     └─ PermissionManager::is_allowed(allow_list)? ─► approved
        ├─ on_tool_call callback registered? ───────► approved (see below)
        └─ otherwise ───────────────────────────────► "Permission denied"
  │
  ▼
ToolExecutor::execute_tool → ServerManager::execute   (server_manager.cpp:153)
  └─ PermissionManager::is_denied(deny_list)? ──────► "Error: Permission denied for <tool>"
  └─ route_tool_call → MCP server runs
```

**What decides it**

- The allow list (or `auto_approve`) skips the prompt. Anything else that has a callback registered also goes through, because `check_approval` sets `approved = true` after calling `on_tool_call`. That callback returns `void` (`engine_types.h:370`), so it can notify the host but cannot veto. Without a callback and without an allow match, the call is denied.
- The deny list is checked again in `ServerManager::execute`, after approval. It wins over `auto_approve` and over the allow list, so a denied tool never reaches the server.

**What a pattern does** (`permission_manager.cpp:101`)

- Each pattern is split at the first `:`. The left side is an fnmatch against the fully-qualified tool name, for example `filesystem.*` or `git.commit`.
- With no `:`, a match on the tool name is enough, so the pattern covers every argument set.
- With a `:`, the right side is fnmatch'd against the full `tool:args` string, for example `bash.execute:python*`.
- For bash, `BashServer::get_permission_pattern` builds `tool:<first word of command> *`, so `bash.execute:python *` allows any `python` command.
- For other tools, the default `get_permission_pattern` returns the bare tool name (`server_base.cpp:87`), so tool-level granularity is the default.
- `is_denied` and `is_allowed` both use `pattern_matches`, so deny and allow patterns use identical syntax.

**Where the lists come from**

- Both lists are read from the config's `permissions.allow` and `permissions.deny` keys (`loader.cpp:369`).
- Runtime "Always Allow/Deny" choices are written back to the project YAML by `PermissionPersister` (`permission_persister.cpp:232`).

**Discrepancy:** the header (`permission_manager.h:6`) says tools "must be explicitly allowed or approved via callback". In the code, any registered callback approves the call, because its return value is never read. Only the absence of a callback causes a default deny. If the host expects the callback to be a real prompt that can refuse, it cannot do that today. I did not check the host-side callback implementation.