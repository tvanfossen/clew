**Short answer:** a call runs only if it clears every precondition in `ToolExecutor`, the approval step, and then the deny check at dispatch in `ServerManager`. The allow list and `auto_approve` are not the only things that decide it.

## The path a call takes

```
model emits ToolCall
 └─ ToolExecutor::check_call_preconditions          (src/mcp/tool_executor.cpp:667)
     1. anti-spiral hard block                       (issue #14, runs first)
     2. check_schema          → args vs JSON schema
     3. check_mcp_authorization → MCP key access level for locked tier
     4. check_tier_allowed    → tier's allowed_tools (gh#83)
     5. check_duplicate       → repeated identical call
     6. check_approval_pc → check_approval             (tool_executor.cpp:161)
          approved = auto_approve_tools
                  || allow-list match
          if !approved and on_tool_call callback set → approved = true
          if !approved → "Permission denied"
 └─ execute_tool → ServerManager::execute            (server_manager.cpp:153)
     7. is_denied(tool, "tool:firstArg") → deny-list match → "Permission denied", never routed
     8. route_tool_call → the server actually runs
```

Two things decide it:

- **Approval (step 6)** is the only place allow-lists, `auto_approve`, and the callback matter.
- **Deny (step 7)** runs after approval, so it overrides everything. A call in both lists, or one allowed by `auto_approve`, is still blocked if it matches a deny pattern.

## What a pattern does

Patterns are `fnmatch` globs, parsed by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`).

| Pattern | Matches |
|---|---|
| `filesystem.*` | Any tool whose fully-qualified name matches the glob (no arg check). |
| `git.commit` | Exactly that tool. |
| `bash.execute:python*` | `bash.execute` only when its **first argument value** matches `python*`. |

- The text before the first `:` is matched against the tool name.
- If there's a `:`, the full string `tool:argValue` must also match. `argValue` comes from `args_to_pattern` (`server_manager.cpp:426`): the value of the first JSON key if it's a string, otherwise `*`.
- So argument patterns only inspect the first argument. A pattern on a later argument never matches.
- Allow and deny use the same matcher. The allow list is consulted in approval, the deny list at dispatch.

## Configuration and persistence

- `permissions:` in YAML provides `allow`, `deny`, and `auto_approve` (`src/config/loader.cpp:365`).
- `ServerManager` builds its `PermissionManager` from `allow` and `deny` (`server_manager.cpp:35`). `auto_approve` becomes `auto_approve_tools` (`src/facade/entropic.cpp:1489`).
- "Always Allow/Deny" calls `add_permission` at runtime and persists through `PermissionPersister` (`src/storage/permission_persister.cpp`). That is a read-modify-write of the project YAML.

## Things that look wrong

1. **The callback approves unconditionally.** In `check_approval`, if no allow match and no `auto_approve`, but `on_tool_call` is registered, the code calls the callback and then sets `approved = true` (`tool_executor.cpp:168–172`). The callback returns `void` and cannot veto. So a host that registers `on_tool_call` gets notified of every non-allow-listed call, but nothing is ever blocked by the callback. The header (`permission_manager.h:6`) says "approved via callback," which doesn't match. Please confirm whether this is intended. If the callback is meant to gate, that line needs to return the host's answer instead of `true`.
2. **The default-deny claim holds only without a callback.** With no callback and no allow match, the call is denied. The header describes default-deny unconditionally.
3. **`check_approval` runs after `check_duplicate` in `check_call_preconditions`, and `check_dup_or_approval` duplicates that ordering.** I didn't find a live caller for `check_dup_or_approval` in `src/` (grep only shows its definition), so it may be dead code. I didn't verify this beyond grep.