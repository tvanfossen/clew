**Short answer:** the call runs only if it clears a fixed chain of checks in `ToolExecutor`, and the permission lists are consulted at two points: an allow lookup inside the approval step, and a deny lookup inside `ServerManager::execute`, which runs after approval. Deny wins over everything, but the approval step is weaker than its docs suggest.

## The path

```
model emits tool call
  │
  ▼
ToolExecutor::process_single_call          tool_executor.cpp:729
  ├─ PRE_TOOL_CALL hook (can cancel)       :733
  ▼
check_call_preconditions                   :667, in this order
  1. anti-spiral hard block                :938
  2. schema validation                     :640
  3. MCP key set (MCPAuthorizationManager) :575
  4. tier allowed_tools                    :198
  5. duplicate-call detection              :117
  6. approval  ──► check_approval          :161
        auto_ok = config.permissions.auto_approve        (facade/entropic.cpp:1489)
               || ServerManager::is_explicitly_allowed   (server_manager.cpp:286)
        if !auto_ok and on_tool_call set: notify UI, approved = true   (:168-173)
        if !approved: "Permission denied" feedback
  ▼
execute_tool → ServerManager::execute      server_manager.cpp:153
  ├─ is_denied(tool, "tool:argpattern")?   → "Error: Permission denied" result
  ▼
route_tool_call → in-process server or external MCP client
```

Allow lists never skip steps 1–5. Deny is checked after approval, so a denied tool can still trigger a UI prompt before it's refused.

## What a pattern in each list does

Both lists use `PermissionManager::pattern_matches` (`permission_manager.cpp:101`):

- **Split on the first `:`.** The left side is `fnmatch`ed against the tool name. Without a colon, that match is enough, so the rule applies to any arguments.
- **With a colon,** the full `tool:argvalue` string must also match the pattern under `fnmatch`.
- **The argument value** is not the whole argument object. `args_to_pattern` (`server_manager.cpp:426`) uses the value of the first key in the JSON object, and only if it is a string. Otherwise it uses `*`. For a no-args call (`{}`) the value is also `*`.
- **`fnmatch` flags are 0,** so `*` also matches `.` and `/`.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `git.commit` | `git.commit` with any args |
| `bash.execute:python*` | `bash.execute` whose first string arg starts with `python`; does not match a no-args call |
| `*` | everything in an allow list; everything in a deny list (deny-all) |

Config entries come from `permissions.allow` / `permissions.deny` (`loader.cpp:365-371`, `config.h:590-592`). Patterns added at runtime through `add_permission` are deduplicated. `auto_approve` skips the approval step only; deny still applies.

## Things I'd flag

1. **The approval callback never denies.** In `check_approval`, if no allow rule or `auto_approve` applies and an `on_tool_call` callback exists, the code calls it and then sets `approved = true` (`tool_executor.cpp:168-173`). The callback returns nothing, so an unlisted tool runs after notification. Only when no callback is registered does the default-deny (`:184`) apply. The header comment says "approved via callback" and `permission_manager.h` says "default-deny", so this contradicts the documented model. Whether it's intentional, I couldn't tell from the code. Nothing in `src/` sets `on_tool_call`, so it depends on what the embedding app registers.
2. **`BashServer::get_permission_pattern` is dead for permissions.** It is defined (`bash.cpp:200`) and reachable via `ServerManager::get_permission_pattern` (`server_manager.cpp:301`), but nothing calls that function. Both allow and deny go through `args_to_pattern`, so a bash rule matches the first string argument, not the command's base name. The base-name logic has no effect on enforcement.
3. **"First argument" is key-sorted, not model-ordered.** nlohmann::json objects iterate in key order by default, so with `{"command": ..., "cwd": ...}` the pattern is taken from `command` only because `c-o-m` sorts before `c-w-d`. Adding a string arg whose name sorts earlier changes which value the pattern sees. I didn't test this, so treat it as a likely trap rather than a confirmed bug.

I only read code, and I didn't run the test suite. The unit tests I looked at (`server_manager_test.cpp:97`, `tool_calling_loop_test.cpp:168`) cover deny blocking and `auto_approve` with the callback null, which is consistent with the reading above.