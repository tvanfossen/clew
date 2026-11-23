**Short answer:** the call runs if it clears the tier and MCP-key gates, is not a duplicate, and is either in `permissions.allow`, covered by `auto_approve`, or passes the `on_tool_call` callback. The deny list is checked later, inside `ServerManager::execute`, and it overrides everything that came before it.

```
tool call
  │
  ├─ ToolExecutor::check_call_preconditions          (tool_executor.cpp:667)
  │    1. anti-spiral hard block
  │    2. schema validation
  │    3. MCP key access level      ← not a list; independent of allow/deny
  │    4. tier allowed_tools        ← not a list; independent of allow/deny
  │    5. duplicate detection
  │    6. check_approval            ← the allow list lives here
  │         auto_approve OR is_allowed(allow list)  → approved
  │         else if on_tool_call set → callback fires, approved = true
  │         else                    → "Permission denied"
  │
  └─ ServerManager::execute                          (server_manager.cpp:153)
       is_denied(deny list)?  → "Error: Permission denied for <tool>"  (wins)
       else route_tool_call
```

**Where each decision is made**

- **Allow list.** `ServerManager::is_explicitly_allowed` builds `tool:args` and calls `PermissionManager::is_allowed` (`permission_manager.cpp:59`). It returns true on the first matching allow pattern.
- **Deny list.** Only `ServerManager::execute` calls `is_denied` (`server_manager.cpp:159`). Deny therefore beats allow, and it beats `auto_approve`, because `auto_approve` only short-circuits `check_approval`. A deny hit returns an envelope, not a precondition rejection.
- **Auto-approve.** `permissions.auto_approve` is copied into `loop_config.auto_approve_tools` (`facade/entropic.cpp:1489`) and skips the whole list check.
- **Config.** `permissions.allow` and `permissions.deny` are parsed in `config/loader.cpp:369-370` and handed to the `PermissionManager` constructor (`server_manager.cpp:35`).

**What a pattern means**

Matching is `pattern_matches` (`permission_manager.cpp:101`), which uses `fnmatch` without `FNM_PATHNAME`, so `*` also crosses `/` and `:`.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `git.commit` | that tool, any args (no colon means tool name only) |
| `bash.execute:python*` | `bash.execute` whose first argument starts with `python` |
| `bash.execute:*` | `bash.execute` with any argument |

The part before the first `:` is matched against the tool name. The part after it is matched against the argument value. That value comes from `args_to_pattern` (`server_manager.cpp:426`): it is the value of the first key that holds a string, or `*` if the args are empty or unparseable. Because nlohmann objects are key-sorted, "first" means alphabetically first key, not the first key in the JSON the model wrote. For bash, that is `command`, which is what you want.

**Things that surprised me**

1. **The callback does not gate anything.** In `check_approval` (`tool_executor.cpp:168-172`), if `on_tool_call` is set, the callback fires and `approved = true` is set unconditionally. Nothing reads a response. The header says tools are "approved via callback", which describes a gate, but the code is a notification. If a host expects `on_tool_call` to be able to refuse a call, it cannot.
2. **The "always allow / always deny" persistence looks unwired in this checkout.** `ToolApproval` (`engine_types.h:63`) and `PermissionPersistFn` exist, and `PermissionPersister` writes YAML. But `set_permission_persist` has no callers in the index, and I found no `src/` consumer of `ToolApproval`. I did not confirm this by reading the facade line by line.
3. **The bash "always" pattern is not the matching pattern.** `BashServer::get_permission_pattern` (`bash.cpp:200`) saves `bash.execute:<base_cmd> *`. Matching uses the full command from `args_to_pattern`. `python script.py` matches `bash.execute:python *`, but a bare `python` does not.
4. **Preconditions run before the lists.** A tool allowed by `permissions.allow` is still refused by the MCP key or tier `allowed_tools` checks, which come first.

I did not read the call site that invokes `ServerManager::execute` after preconditions pass. I am inferring that every dispatched call goes through it, because `is_denied` has no other caller.