Short answer: the allow and deny lists are consulted at two different points. The allow list only skips the approval prompt. The deny list is checked later, inside `ServerManager::execute`, after approval has already passed.

## Trace

```
model emits tool call
  │
  ▼
ToolExecutor::process_single_call          src/mcp/tool_executor.cpp:729
  1. PRE_TOOL_CALL hook (can cancel)        :733
  2. check_call_preconditions               :667
       a. anti-spiral hard block
       b. schema validation (required/enum/type)
       c. MCP key authorization (only if identity is registered)
       d. tier allowed_tools (gh#83)
       e. duplicate call check
       f. check_approval                    :161
            approved = auto_approve_tools
                    || ServerManager::is_explicitly_allowed   (ALLOW list)
            if !approved and on_tool_call set → callback, approved = true
            else if !approved → "Permission denied"
  3. execute_tool                           :379
       on_tool_start callback fires here
       ServerManager::execute               src/mcp/server_manager.cpp:153
            if is_denied(...)  → "Error: Permission denied for X" (DENY list)
            else route_tool_call → server / external MCP client
```

So a call runs only if it clears the approval gate (step 2f) and is not matched by the deny list (step 3).

## What each list entry does

Entries use `tool_pattern[:arg_pattern]`, matched with `fnmatch` (`src/mcp/permission_manager.cpp:101`).

| Entry | Matches |
|---|---|
| `filesystem.*` | Every tool whose name matches the glob. No `FNM_PATHNAME`, so `*` also crosses dots. |
| `git.commit` | Only that tool, any arguments. |
| `bash.execute:python*` | `bash.execute` where the argument pattern matches `python*`. |

The argument side is not the full argument set. `ServerManager::args_to_pattern` (`server_manager.cpp:426`) takes only the first string-valued argument. An empty or non-string argument set becomes `*`. Since `nlohmann::json` objects iterate their keys in sorted order (I did not confirm the ordered type in this repo), "first" means the alphabetically first string key. A rule like `filesystem.read_file:/safe/*` can therefore be checked against a different argument than the one you meant.

Behavioral consequences:

- **Allow match** sets `approved` and skips the callback. It does not bypass the deny check.
- **Deny match** blocks the call even when it is also on the allow list, and even under `auto_approve: true`. The result is a normal tool result string, not a precondition rejection.
- **Deny is checked after `on_tool_start` fires.** A denied call still appears to the UI as started.
- **Config:** `permissions.allow`, `permissions.deny`, and `permissions.auto_approve` are read in `src/config/loader.cpp:365`.

## Things that contradict the docs

1. **The `on_tool_call` callback cannot deny.** In `check_approval`, a non-allowlisted call with a callback registered gets `approved = true` after the callback returns. The callback is a notification, not a gate. The header comment in `permission_manager.h` ("approved via callback") suggests otherwise. I did not find where the facade sets `on_tool_call`. If the embedder leaves it null, the no-callback path applies and unlisted calls are denied.
2. **`BashServer::get_permission_pattern` is dead code.** It would produce per-base-command patterns like `bash.execute:python *`, but `ServerManager::get_permission_pattern` has no callers. Both `execute()` and `is_explicitly_allowed()` use `args_to_pattern`. Bash rules therefore match against the first string argument, not the parsed base command.

I only read the code and did not run the test suite.