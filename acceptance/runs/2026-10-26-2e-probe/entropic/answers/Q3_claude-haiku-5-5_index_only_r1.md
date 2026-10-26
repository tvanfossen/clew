**Short answer:** the allow and deny lists don't decide alone. A call passes several gates in `ToolExecutor`, and the deny list is only enforced later, inside `ServerManager::execute`. Patterns are `tool:arg` globs. I answered from the index alone, so the bodies below are as indexed, not re-read from source.

**The path a call takes**

```
process_single_call
 └─ check_call_preconditions          (tool_executor.cpp:667)
     1. anti-spiral hard block        → rejected_anti_spiral
     2. check_schema                  → rejected_schema
     3. check_mcp_authorization       → rejected_precondition
     4. check_tier_allowed            → rejected_unauthorized (tier allowed_tools)
     5. check_duplicate               → rejected_duplicate
     6. check_approval_pc             → "Permission denied" if check_approval is false
 └─ execute_tool → ServerManager::execute   (server_manager.cpp:153)
     7. is_denied(tool, tool:firstArg) → "Error: Permission denied for <tool>"
     8. route_tool_call               → the tool actually runs
```

**What `check_approval` does** (`tool_executor.cpp:161`)

- `approved = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(name, args)`.
- If that is false and an `on_tool_call` callback is wired, the callback is invoked and `approved` is then set to `true` unconditionally. The callback works as a notification, not a gate.
- If there is no callback, the call is denied.
- It fires `ON_PERMISSION_CHECK` as an informational hook either way.

**Where the lists are consulted**

- `is_explicitly_allowed` builds `tool_name + ":" + args_to_pattern(args)` and checks the allow list only (`server_manager.cpp:286`).
- `ServerManager::execute` checks the deny list only (`server_manager.cpp:153`). A denied call is refused even if auto-approve or the callback said yes.
- So with a callback wired, the only real gate for a non-allow-listed call is the deny list, and a deny-listed call is still refused at step 7.

**What a pattern means** (`PermissionManager`, `permission_manager.cpp`)

- **Format:** `tool[:argpattern]`. Both parts are `fnmatch` globs with flags 0, so `*` also matches `/` and `:`.
- **Tool part:** matched against the fully-qualified tool name, e.g. `filesystem.read_file`.
- **No colon** (`filesystem.*`): matches that tool with any arguments.
- **With colon** (`bash.execute:pytest *`): the tool part must match, then the full `tool:arg` string must match the glob.
- **Arg value:** `args_to_pattern` takes the first string-valued member of the args JSON object, or `*` if the args are empty, non-object, or unparseable. With nlohmann's default object ordering this is probably the alphabetically first key, which I did not verify.
- **Per-server granularity:** `MCPServerBase::get_permission_pattern` returns the bare tool name by default. Subclasses override it for finer control. `BashServer` overrides it, but the index did not resolve that override's body.
- **Default:** no allow or deny match means default-deny, so an unlisted call needs approval (auto-approve or a callback).

**Other notes**

- Adding a rule at runtime (`PermissionManager::add_permission`, or `PermissionPersister::save_permission`) writes into `permissions.allow` / `permissions.deny` in `config.local.yaml`. The persister is a line-based YAML edit, and it is a no-op if the pattern is already present.
- **Doc/code mismatch:** the `permission_manager.h` header says tools "must be explicitly allowed or approved via callback", but `check_approval` approves on any callback. If the header is the intended contract, `check_approval` has a bug. If the code is intended, the header is stale.