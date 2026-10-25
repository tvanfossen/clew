## What decides whether a tool call runs

Five gates run in order. The allow and deny lists act at different points.

```
PRE_TOOL_CALL hook          tool_executor.cpp:857   hook returns nonzero → cancelled
  │
anti-spiral hard block      tool_executor.cpp:938   projected same-tool count ≥ threshold → rejected
  │
schema validation           tool_executor.cpp:640   bad args → rejected
  │
MCP key / access level      tool_executor.cpp:575   identity lacks access → rejected
  │
tier allowed_tools          tool_executor.cpp:198   tier allowlist excludes tool → rejected
  │
duplicate call              tool_executor.cpp:117   same name+args seen → rejected
  │
check_approval()            tool_executor.cpp:161
  │   auto_ok = permissions.auto_approve  OR  allow-list matches
  │   if !auto_ok and on_tool_call callback set → callback(), approved = true
  │   if !auto_ok and no callback              → "Permission denied"
  │
ServerManager::execute()    server_manager.cpp:153
  │   deny-list matches → "Error: Permission denied for <tool>"   (the real veto)
  │
route_tool_call → server
```

Two things in this trace are not what the header comments promise:

1. **The approval callback cannot refuse a call.** `on_tool_call` is `void(*)(const char*, void*)` (`engine_types.h:370`). `check_approval` sets `approved = true` whenever the callback exists, so the frontend's prompt is a notification, not a gate. `permission_manager.h:7` says tools are "approved via callback", which is not how it works.
2. **The deny list is the only real block, and it runs after approval.** A deny-listed call that is not on the allow list still fires the callback, so the user is prompted for a call that will be refused anyway. The deny message is also a plain `Error: Permission denied` result, not the `create_denied_message` text, so the model doesn't get the "do not retry" instruction.

Also, `auto_approve` does not bypass the deny list. `execute()` checks deny unconditionally.

## What a pattern means

Format is `tool[:arg-glob]`, split at the first colon (`permission_manager.cpp:101-125`).

| Pattern | Matches |
|---|---|
| `filesystem.*` | Any filesystem tool, any args (tool part is fnmatch'd) |
| `bash.execute` | That tool, any args (no colon, so args are ignored) |
| `bash.execute:python*` | `bash.execute` whose first string arg starts with `python` |
| `*` | Every tool. Empty args produce the pattern `*` (`server_manager.cpp:428`). |

Details that matter:

- **Only one argument is inspected.** `args_to_pattern` (`server_manager.cpp:426`) takes the first string-valued argument, not all of them. Under nlohmann's default sorted object, that is usually the alphabetically first key. So `filesystem.write_file:/safe/*` does not constrain `path` if `content` sorts first.
- **Globs are not path- or shell-aware.** `fnmatch` runs with flags 0, so `*` crosses `/`, spaces and `;`. `bash.execute:python*` matches `python3 x.py; rm -rf ~`. That is a real hole for shell commands.
- **Deny beats allow, but only in effect.** Allow skips the prompt. Deny blocks at execute time no matter what.
- **Duplicates are ignored.** `add_permission` skips patterns already in the list (`permission_manager.cpp:79-90`).
- **Where lists come from.** `permissions.allow`, `permissions.deny`, `permissions.auto_approve` in config (`loader.cpp:369-370`, `config.h:589-593`). `auto_approve` feeds `LoopConfig.auto_approve_tools` (`entropic.cpp:1489`). The lists seed `ServerManager` (`server_manager.cpp:35`). `ALWAYS_ALLOW`/`ALWAYS_DENY` answers are written back to project config through `PermissionPersister`. I did not trace who calls the persister.

One more finding: `BashServer::get_permission_pattern` (`bash.cpp:200`) is never called from the gate. Both `execute` and `is_explicitly_allowed` build the pattern with `args_to_pattern`, so any per-server pattern logic is dead code for permissions.

I did not build or run the test suite. The trace is from reading `tool_executor.cpp`, `server_manager.cpp`, `permission_manager.cpp` and the headers.