**Short answer:** the call runs unless it is stopped at one of several gates, in this order. The allow list and `auto_approve` decide whether the user is prompted. The deny list is enforced later, at execution, so it still applies even when prompting is skipped.

```
tool call from model
  │
  ├─ PRE_TOOL_CALL hook ............ ToolExecutor::process_single_call (tool_executor.cpp:733)
  │     cancelled? → "Cancelled by hook"
  ├─ anti-spiral block, schema check
  ├─ MCP key check ................. check_mcp_authorization (tool_executor.cpp:575)
  ├─ tier allowed_tools ............ check_tier_allowed (tool_executor.cpp:198)
  ├─ duplicate-call check
  ├─ APPROVAL ...................... check_approval (tool_executor.cpp:161)
  │     auto_ok = auto_approve_tools || is_explicitly_allowed(allow list)
  │     if !auto_ok and on_tool_call callback set → approved = true (callback fires)
  │     else → "Permission denied"
  ├─ execute_tool → ServerManager::execute (server_manager.cpp:153)
  │     DENY LIST: is_denied(...) → "Error: Permission denied for <tool>"
  └─ route_tool_call → in-process server or external MCP client
```

**What each list is**

- **`permissions.allow`** — patterns that skip the prompt. Only consulted in `check_approval`, and only when `auto_approve` is off.
- **`permissions.deny`** — patterns that block the call. Checked in `ServerManager::execute`, after approval, so it overrides `auto_approve`.
- **`permissions.auto_approve`** — a bool, wired to `LoopConfig::auto_approve_tools` (`facade/entropic.cpp:1489`). When true, every call skips the prompt, but deny still applies.
- **`permission_persist_`** — "Always Allow/Deny" choices are written back into `permissions.allow` / `deny` in the project YAML by `PermissionPersister`.

**Pattern grammar** (`permission_manager.cpp:101`)

The pattern is split at its first `:`. The left side matches the tool name and the right side matches the first string argument value, both with `fnmatch`.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `bash.execute` | that tool, no arg check (no colon) |
| `bash.execute:python*` | `bash.execute` whose first string arg starts with `python` |
| `bash.execute:git *` | `bash.execute` whose first string arg starts with `git ` |

The arg value comes from `args_to_pattern` (`server_manager.cpp:426`), which takes only the first string-valued argument, not all of them. `fnmatch` runs with flags 0, so `*` also crosses `/`.

**Things that differ from what the docs suggest**

1. **The callback cannot deny.** `check_approval` sets `approved = true` whenever `on_tool_call` is registered, and the callback returns nothing. So with a UI attached, the effective default is "allow and notify", not the "default-deny, approved via callback" described in `permission_manager.h:6`. Only the absence of a callback produces a denial.
2. **Deny-listed calls can still prompt.** Because deny is checked after approval, a deny-listed call with a callback is shown to the user and then blocked anyway. The two blocks also return different messages: "Permission denied" from approval versus "Error: Permission denied for X" from execution.
3. **Argument matching is shallow.** Only the first string arg is matched, so a deny pattern on `bash.execute:rm*` will not catch `command` values that do not start with `rm`, and the deny pattern only sees whichever arg is first.

I did not run anything or change any files. The duplicate-call and anti-spiral gates were read only as far as their ordering in `check_call_preconditions`.