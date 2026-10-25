**Short answer:** the call is gated by a fixed chain in `ToolExecutor`. Config lists only feed into it at two points, and the approval step is weaker than the header comments say. The allow list is consulted at approval time, the deny list only at execute time, and an `on_tool_call` callback approves the call rather than gating it.

## The path

```
model emits tool call
  │
  ├─ fire_pre_tool_hook ─────────────── hook can cancel ("Cancelled by hook")
  │
  └─ check_call_preconditions           (src/mcp/tool_executor.cpp:667)
       1. check_anti_spiral_hard_block  consecutive-call cap
       2. check_schema                  argument validation
       3. check_mcp_authorization       MCP key access level
       4. check_tier_allowed            locked tier's allowed_tools
       5. check_duplicate               same call already run
       6. check_approval_pc → check_approval   ◄── permission lists live here
  │
  ├─ execute_tool → ServerManager::execute    (server_manager.cpp:153)
  │     is_denied(tool, "tool:args")? ──yes──► "Error: Permission denied"
  │     route_tool_call
  │
  └─ finalize_tool_call
```

**Approval (`check_approval`, tool_executor.cpp:161):**

```
auto_ok = loop_config.auto_approve_tools
          || ServerManager::is_explicitly_allowed(name, args)   → PermissionManager::is_allowed
approved = auto_ok
if (!approved && callbacks.on_tool_call != nullptr):
    on_tool_call(json)          // void return, cannot veto
    approved = true             // ◄── unconditional
if (!approved) → "Permission denied" rejection
```

## What decides it

- **`auto_approve: true`** (`permissions.auto_approve`, mapped at `facade/entropic.cpp:1489`) skips the allow list entirely. Deny still applies at execute.
- **Allow list hit** approves the call with no callback involved.
- **Deny list hit** is only checked in `ServerManager::execute`, after approval has already passed. The call is refused there.
- **No allow hit, callback registered** → approved anyway. The callback is a notification, not a gate.
- **No allow hit, no callback** → denied with `Permission denied`.

## What a pattern does

Both lists use `PermissionManager::pattern_matches` (permission_manager.cpp:101), which uses `fnmatch` with no flags:

- `"filesystem.*"` has no colon, so it matches the tool name only and every args value passes.
- `"bash.execute:python*"` splits at the colon. The tool part must match the name, and the full `tool:args` string must also match, where args come from `args_to_pattern` (I did not read that function's body).
- `*` is not path-aware, so it also matches dots and slashes.
- Allow patterns are checked in order and the first hit returns true. Deny patterns work the same way.

The "Always Allow/Deny" options write patterns back to the YAML `permissions.allow` / `permissions.deny` lists through `PermissionPersister`.

## Where the code disagrees with its docs

1. **"Default-deny" is false when a callback is wired.** `permission_manager.h:6` says tools must be allowed or approved, but any call that isn't allow-listed is approved once a callback exists. The callback cannot block it.
2. **A denied tool can report `"allowed"`.** The `ON_PERMISSION_CHECK` hook is fired from `check_approval` before the deny list is consulted, so a deny-listed call with a callback set reports `allowed` and then fails at execute.
3. **Deny-list rejections skip the feedback message.** `ServerManager::execute` returns a plain `Error: Permission denied` result. It does not go through `create_denied_message`, so the "Do NOT retry" guidance is missing and the result is not typed as a precondition rejection.

I did not run anything; these come from reading the source paths above. Points 1 and 2 would be the first things to check if permissions behave unexpectedly.