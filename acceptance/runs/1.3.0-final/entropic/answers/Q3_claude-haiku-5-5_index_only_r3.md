The call is decided by two gates in `ToolExecutor` and `ServerManager`. Deny is checked again at execution time, so a deny pattern can block a call that approval let through.

```
model emits tool call
  └─ ToolExecutor::execute_tool / check_dup_or_approval
       └─ check_approval(call)                       [tool_executor.cpp:161]
            ├─ loop_config.auto_approve_tools?  ──yes──► approved
            ├─ ServerManager::is_explicitly_allowed
            │     └─ PermissionManager::is_allowed(allow list)  ──match──► approved
            ├─ on_tool_call callback set?  ──yes──► approved = true (no return value read)
            └─ otherwise ──► "Permission denied" message, call never runs
       └─ ServerManager::execute(name, args)          [server_manager.cpp:153]
            ├─ PermissionManager::is_denied(deny list) ──match──► "Permission denied" result
            └─ route_tool_call ──► server runs the tool
```

**What decides it**

1. **Approval (`check_approval`).** Passes if `auto_approve_tools` is set (default `false`), or if the allow list matches. Otherwise it calls the `on_tool_call` callback if one is registered. Two things stand out:
   - The callback is `void(*)(const char*, void*)`, so it cannot return a verdict. `check_approval` sets `approved = true` immediately after calling it. In this code, a registered callback approves every call and only notifies. The header calls the model "approved via callback", which describes intent, not behaviour. I'd treat this as a likely bug and check it against the tests.
   - With no callback and no allow match, the call is denied.
2. **Deny (`ServerManager::execute`).** Runs after approval, so a deny pattern blocks a call even when it was approved. `is_allowed` does not consult the deny list, so "deny wins" is enforced only here. A pattern in both lists is approved but still blocked.

**What a pattern does**

- Patterns are `fnmatch` globs (`fnmatch` with flags 0, so `*` also matches `/`).
- A pattern with no colon (`filesystem.*`) matches the tool name only.
- A pattern with a colon (`bash.execute:git *`) splits at the first `:`. The tool half must match the tool name. The argument half must match the full key `tool:arg`.
- The argument in that key comes from `ServerManager::args_to_pattern`: the first string-valued argument, or `*` if the arguments are empty or unparseable.
- `BashServer::get_permission_pattern` returns `tool:base_cmd *` (e.g. `bash.execute:git *`). The index shows this is used to generate the "Always Allow/Deny" pattern to persist, not in the match itself. The match uses the raw first argument, and the glob `git *` matches `git status`.
- Allow lists are checked with `is_allowed`; deny lists with `is_denied`. Both use the same `pattern_matches`.

**Configuration**

`PermissionsConfig` has `allow`, `deny` (glob lists) and `auto_approve`, parsed by `parse_permissions_config`. Runtime additions go through `add_permission`, and `PermissionPersister` writes them back to the YAML config.

**Not verified:** I did not confirm that `PermissionsConfig.auto_approve` is copied into `LoopConfig.auto_approve_tools`, or where the config lists are passed to `PermissionManager`. The index only shows `ServerManager` takes the permission config in its constructor.