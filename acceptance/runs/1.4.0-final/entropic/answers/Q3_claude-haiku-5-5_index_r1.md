**Short answer:** the approval gate is `ToolExecutor::check_approval`, and the deny list is enforced a second time in `ServerManager::execute`. The allow list only skips the prompt. Two of the pieces don't behave the way their comments say, which matters if you rely on them.

## Flow

```
tool call
 │
 ├─ ToolExecutor::check_call_preconditions          tool_executor.cpp:667
 │    anti-spiral block → schema → MCP authorization → tier allowed_tools
 │    → duplicate check → check_approval_pc
 │
 ├─ ToolExecutor::check_approval                    tool_executor.cpp:161
 │    auto_ok = loop.auto_approve  OR  ServerManager::is_explicitly_allowed(allow list)
 │    if !auto_ok and on_tool_call wired → callback fires, approved = true
 │    fire ON_PERMISSION_CHECK hook (informational)
 │    if !approved → "Permission denied"
 │
 └─ ServerManager::execute                          server_manager.cpp:153
      is_denied(deny list)? → "Error: Permission denied for <tool>" result
      else route_tool_call → in-process server or external MCP client
```

Config is read in `parse_permissions_config` (`loader.cpp:365`) into `PermissionsConfig` (`types/config.h:589`). `ServerManager` builds its `PermissionManager` from the allow and deny lists (`server_manager.cpp:35`). `auto_approve` is copied into the loop config (`facade/entropic.cpp:1489`).

## What a pattern means

Format is `tool` or `tool:arg`. Matching uses `fnmatch` with no flags, so `*` also crosses `/`.

- **No colon** (`filesystem.*`, `git.status`): matches on the fully-qualified tool name only.
- **With colon** (`bash.execute:python*`): the tool part must match, then the arg part is matched against `tool:<first string argument>`. Calls with no args, or a non-string first arg, present `*`. (`permission_manager.cpp:101`, `server_manager.cpp:426`)
- `*` in the allow list auto-approves everything. `*` in the deny list blocks everything.

Examples from the repo:

- `filesystem.*` in allow: every filesystem tool skips the prompt.
- `bash.execute` in deny: every bash.execute call is blocked (`tests/data/comprehensive_config.yaml:93`).
- `bash.execute:python*` in allow: only commands whose first argument starts with `python`.

## Discrepancies found

1. **Config key names disagree.** The loader and `PermissionsConfig` use `allow` / `deny` (`loader.cpp:369`). `data/schemas/config_schema.json:61-62` documents `allow_patterns` / `deny_patterns`. A config written to the schema names would not be read by the loader. I did not run that config to confirm the failure mode.
2. **The approval callback never denies.** `check_approval` sets `approved = true` right after calling `on_tool_call`, and the callback returns `void`. The header comment says tools are "approved via callback" (`permission_manager.h:6`), but a wired prompt cannot reject a call. Denial happens only at `ServerManager::execute`.
3. **Deny is not checked during approval.** `is_allowed` never consults the deny list. So a denied tool still gets the prompt callback and still counts as approved when `auto_approve` is on. It is then stopped at execute with a result string, not `ENTROPIC_ERROR_PERMISSION_DENIED`.
4. **Persistence is not reached.** `permission_persist_` is set (`tool_executor.cpp:51`), and `get_permission_pattern` is defined in `ServerManager` and `BashServer`. I found no caller in the call path, so "Always Allow/Deny" persistence does not appear to be wired into the flow.

I did not trace `check_mcp_authorization` (the identity/key layer, `mcp_authorization.cpp:139`). It runs before approval, so it can reject a call before any of the above is consulted.