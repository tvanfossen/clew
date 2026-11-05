**Short answer:** the call runs only if it survives a chain of checks in `ToolExecutor`. The permission lists decide only the approval step, and the deny list is enforced a second time at execution. One consequence needs your attention: with a callback registered, the approval step grants any call that is not on the allow list.

## The path a call takes

```
tool call
 → PRE_TOOL_CALL hook (can cancel)                       tool_executor.cpp:733
 → check_call_preconditions                              tool_executor.cpp:667
     anti-spiral hard block → schema → MCP key auth
     → tier → duplicate → check_approval_pc
         → check_approval                                tool_executor.cpp:161
             auto_approve OR is_explicitly_allowed (allow list)
             else if on_tool_call callback set → approved = true
             else → denied ("Permission denied")
 → execute_tool → ServerManager::execute                 tool_executor.cpp:398
     is_denied (deny list) → "Permission denied" result  server_manager.cpp:159
     else route_tool_call
```

The permission lists are read in two places: `check_approval` for allow and `ServerManager::execute` for deny. The deny check in `execute` is the authoritative gate, since nothing reaches a server without passing it.

## The approval step has a gap

`check_approval` (`tool_executor.cpp:161-188`) sets `approved = true` after calling `on_tool_call`. That callback is typed `void` (`engine_types.h:370`), so the engine never receives a yes or no from the consumer.

- With no callback and no allow match, the call is denied.
- With a callback and no allow match, the call is approved, and the callback is only a notification.
- The deny list is not consulted in this step. A denied tool with a callback still triggers the prompt, the answer is ignored, and then `execute` refuses it.

The header says "Tools must be explicitly allowed or approved via callback" (`permission_manager.h:6-7`). The code cannot express a callback denial, so either the callback should return a bool or the header is wrong. I read this from the source and did not run it, so please confirm the intent before I change anything.

## What each pattern does

Patterns are strings in `permissions.allow` and `permissions.deny`, with optional `auto_approve` (`config.h:589`, `loader.cpp:367`). Matching is in `PermissionManager::pattern_matches` (`permission_manager.cpp:101`):

| Pattern | Matches |
|---|---|
| `filesystem.*` | Every filesystem tool, any arguments (fnmatch glob on the tool name) |
| `git.commit` | That tool with any arguments (no colon means tool-only match) |
| `bash.execute:python*` | `bash.execute` only when the first argument value starts with `python` |

Rules that follow from the code:

- The part before the first `:` is matched against the tool name. If there is a colon, the whole string is matched against `tool:<argvalue>`.
- The argument value is `args_to_pattern` (`server_manager.cpp:426`): the value of the first JSON member if it is a string, otherwise `*`. "First" is nlohmann's default key order, which is alphabetical. I inferred this from the default `nlohmann::json` type, since the source never uses `ordered_json`. A deny like `filesystem.write:/etc/*` therefore checks whichever argument sorts first, not `path`.
- Shell commands are the main gap. `BashServer::get_permission_pattern` (`bash.cpp:200`) persists `bash.execute:<base_cmd> *`, so `git *` allows `git status && rm -rf x`, because fnmatch `*` matches anything, including `;`.
- Matching is first-hit in list order, with no specificity ranking. Deny wins only because `execute` checks it after approval.
- "Always Allow/Deny" calls `add_permission` (`server_manager.cpp:361`) and persists through `PermissionPersister`, which writes `config.local.yaml`. I did not trace the persister in detail.

Questions for you: should a callback be able to deny, and should `check_approval` check the deny list before prompting?