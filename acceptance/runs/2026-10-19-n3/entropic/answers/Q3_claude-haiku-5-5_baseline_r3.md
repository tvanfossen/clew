## What decides whether a tool call runs

Two lists, one switch, and a deny check that runs late. The path for one call:

```
model emits tool call
 └─ ToolExecutor::process_single_call          tool_executor.cpp:729
     ├─ PRE_TOOL_CALL hook (can cancel)        :733
     ├─ check_call_preconditions               :667
     │   ├─ anti-spiral hard block             :673
     │   ├─ schema validation                  :677
     │   ├─ MCP key authorization              :680
     │   ├─ tier allowed_tools                 :684
     │   ├─ duplicate-call check               :687
     │   └─ check_approval  (allow list / callback)   :691, :161
     └─ execute_tool → ServerManager::execute  :379, :397
         └─ is_denied(deny list)  → "Error: Permission denied"   server_manager.cpp:158-159
            └─ route to in-process or external server
```

The allow decision is in `check_approval` (`tool_executor.cpp:161-188`):

1. `auto_ok = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(...)`. `auto_approve` comes from `permissions.auto_approve` (`facade/entropic.cpp:1489`).
2. If that is false and an `on_tool_call` callback is set, the code sets `approved = true` unconditionally (`:168-173`). The callback's return is void, so the frontend cannot veto anything.
3. If there is no callback, the call is denied (`:184-186`). The test at `tests/unit/mcp/tool_executor_test.cpp:280` pins this headless behaviour.

The deny list is not consulted in `check_approval`. It is checked only inside `ServerManager::execute`, after approval has already passed. So `deny` beats `allow` and `auto_approve` in practice, but only at dispatch time.

## What a pattern does

Patterns are parsed in `PermissionManager::pattern_matches` (`permission_manager.cpp:101-125`) and stored from config `permissions.allow` / `permissions.deny` (`config/loader.cpp:365-371`, `server_manager.cpp:35`).

- **`tool`** (no colon): `fnmatch` on the fully-qualified tool name. `filesystem.*` covers every filesystem tool.
- **`tool:argpattern`**: the part before the first `:` is matched against the tool name. The part after is matched with `fnmatch` against `tool_name:<arg>`, where `<arg>` comes from `args_to_pattern` (`server_manager.cpp:426-443`). `bash.execute:python*` therefore matches when the command starts with `python`.

Two gotchas in `args_to_pattern`:

- It only inspects the first key of the args object. nlohmann::json objects are sorted by key by default, so "first" means alphabetically first, not the order the model wrote them. If that value is not a string, the subject becomes `*`.
- Because the subject becomes `tool:*`, a deny like `bash.execute:rm*` does not match in that case. The deny fails open. This is a real hole if the first-key argument is not the one you meant to guard.

Allow and deny semantics:

| List | Where it is checked | Effect on match |
|---|---|---|
| `allow` | `check_approval` via `is_explicitly_allowed` | Skips the approval callback. Does not bypass the deny check. |
| `deny` | `ServerManager::execute` via `is_denied` | Returns `"Error: Permission denied for <tool>"` as the tool result. The call is never routed. |

## Things that look wrong

- **Header vs. code.** `permission_manager.h:6-7` says tools are "approved via callback" under default-deny. The code grants approval whenever a callback is wired, so every unlisted tool runs once a frontend registers `on_tool_call`. The `ON_PERMISSION_CHECK` hook then reports `"allowed"` for those calls (`tool_executor.cpp:176-182`).
- **Per-command bash patterns are dead code.** `ServerManager::get_permission_pattern` (`server_manager.cpp:301`, implemented in `bash.cpp:200`) is never called. The permission path builds its subject from `args_to_pattern`, not the server's pattern, so bash-specific matching is not used.
- **Denied calls still fire callbacks.** `on_tool_start` and the hooks run before the deny check, and `record_tool_history` records the call.

I did not trace the `PermissionPersister` (`storage/permission_persister.cpp`) path that may write new allow entries at runtime, or how the frontend's `on_tool_call` is wired in practice. Both are outside what the question asked, and I did not confirm either.