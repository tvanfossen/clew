## What decides whether a tool call runs

Two checks decide it, in different places: an **approval** gate that runs before execution, and a **deny** gate that runs inside `ServerManager::execute`. Approval is where the allow list lives, and it can be bypassed by a callback. Deny is the only check that can't be bypassed.

```
ToolExecutor::process_single_call          tool_executor.cpp:729
 │
 ├─ PRE_TOOL_CALL hook ──── cancel? ──────────────────────────► rejected
 │
 ├─ check_call_preconditions               tool_executor.cpp:667
 │   ├─ anti-spiral hard block
 │   ├─ schema
 │   ├─ MCP authorization
 │   ├─ tier allowed
 │   ├─ duplicate detection
 │   └─ check_approval_pc → check_approval  tool_executor.cpp:161
 │        auto_ok = loop.auto_approve_tools            (permissions.auto_approve)
 │                  || ServerManager::is_explicitly_allowed → PermissionManager::is_allowed
 │        if !auto_ok && on_tool_call callback set:
 │            callback(...); approved = TRUE            ← always approves
 │        else approved = auto_ok
 │        !approved → "Permission denied"  ─────────────────────► rejected
 │
 └─ execute_tool → ServerManager::execute  server_manager.cpp:153
      is_denied(tool, pattern)? ──yes──► "Error: Permission denied for <tool>"
      route_tool_call → server
```

What this means in practice:

- **The allow list only skips the prompt.** It doesn't grant anything by itself beyond skipping the callback.
- **The deny list is the hard gate.** It is checked last, in `execute`, so it applies even to calls that `auto_approve` or the allow list already approved. `auto_approve` does not bypass deny.
- **The callback approves unconditionally.** `check_approval` calls `on_tool_call` (a `void` function that returns nothing) and then sets `approved = true`. With that callback wired, the only calls refused at approval are the ones that hit the deny list later. This contradicts the header's "default-deny" wording (`permission_manager.h`). A call only gets the literal "Permission denied" at the approval stage when there is no callback, no allow match and `auto_approve` is off. I read this from the source; I did not confirm whether every frontend sets `on_tool_call`.
- **A call on both lists** passes approval through the allow match, then is blocked in `execute`. The callback never fires for it.
- **Denials come back as tool results**, not exceptions. The model sees the error text.

## What a pattern means

Config keys are `permissions.allow`, `permissions.deny` and `permissions.auto_approve` (`src/config/loader.cpp:365`). Allow and deny entries use the same matcher, `PermissionManager::pattern_matches` (`permission_manager.cpp:101`):

1. Split the entry at the first `:`.
2. The left side is an `fnmatch` glob matched against the fully-qualified tool name. With no `:`, the tool-name match is enough.
3. The right side is an `fnmatch` glob matched against `tool_name:<value>`, where `<value>` comes from `args_to_pattern`. That is the first string-valued argument in the JSON args, or `*` if there are no args, the first value isn't a string, or parsing fails.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `git.commit` | the tool, any args (no colon) |
| `bash.execute:python*` | bash calls whose first argument starts with `python` |
| `bash.execute:ls *` | bash calls whose command starts with `ls ` |

The `*` in `fnmatch` also matches `/`, `;` and spaces, so `bash.execute:ls *` also matches `ls; rm -rf /`. Glob patterns on shell commands don't stop command chaining. That is a real weakness for allowing bash.

## Gaps I noticed

- `BashServer::get_permission_pattern` builds `bash.execute:<base> *`, and `ServerManager::get_permission_pattern` delegates to it. The index shows no production caller of `ServerManager::get_permission_pattern`, only tests. Matching uses `args_to_pattern`, not that method. I didn't trace the UI side that creates "Always Allow" entries, so I can't say whether the two shapes ever disagree.

I read this statically. I didn't build or run anything.