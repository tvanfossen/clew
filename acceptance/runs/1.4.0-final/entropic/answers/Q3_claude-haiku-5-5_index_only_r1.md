**Short answer:** a call runs only if it clears every precondition in `ToolExecutor`, the approval step must find an allow match or a registered `on_tool_call` callback, and `ServerManager::execute` must not hit a deny match. Deny is the only list that can block a call that approval already passed.

## Trace

```
process_single_call                       (tool_executor.h:729)
 ├─ PRE_TOOL_CALL hook  ──────────────► cancel ("Cancelled by hook")
 ├─ check_call_preconditions             (:667)
 │   ├─ anti-spiral hard block
 │   ├─ check_schema
 │   ├─ check_mcp_authorization
 │   ├─ check_tier_allowed
 │   ├─ check_duplicate
 │   └─ check_approval_pc → check_approval (tool_executor.cpp:161)
 │        approved = auto_approve_tools
 │                || ServerManager::is_explicitly_allowed  → PermissionManager::is_allowed
 │        if !approved and on_tool_call != null → approved = true
 │        else → "Permission denied"
 ├─ execute_tool                         (:379)
 │   └─ ServerManager::execute           (server_manager.cpp:153)
 │        pattern = tool + ":" + args_to_pattern(args)
 │        is_denied(tool, pattern) → "Error: Permission denied for <tool>"
 │        else route_tool_call → the MCP server runs
 └─ finalize_tool_call
```

Three observations from the trace:

- **Deny is enforced last, and always.** It sits in `execute`, after approval, so `auto_approve` cannot bypass it.
- **The callback approves unconditionally.** `check_approval` sets `approved = true` whenever `on_tool_call` is non-null. It does not read a return value. So with no allow match, the call runs if a callback is registered, and a deny match still stops it in `execute`. The header comment says "approved via callback", which matches this, but the callback's contract is worth checking in the C API docs. I could not verify that from the index.
- **Config is parsed in `parse_permissions_config`** (`src/config/loader.cpp:365`). It fills `PermissionsConfig` (`types/config.h:589`) with `allow`, `deny` (glob lists) and `auto_approve` (bool). I did not trace how that struct reaches the `PermissionManager` constructor.

## What a pattern does

Matching is in `PermissionManager::pattern_matches` (`permission_manager.cpp:101`), using `fnmatch`:

1. Split the entry at the first `:`.
2. The left side is a glob on the tool name. It must match.
3. If there is no `:`, the tool-name match alone is enough, for any arguments.
4. If there is a `:`, the right side is a glob on the argument pattern, matched against `tool:<arg>`.

The argument value comes from `args_to_pattern` (`server_manager.cpp:426`). It takes the first JSON value of the arguments if that value is a string, and `*` otherwise. So `filesystem.read_file` matches any read; `filesystem.read_file:/etc/*` matches reads under `/etc`; `*` matches every tool.

Examples:

| Entry | Effect |
|---|---|
| `filesystem.read_file` | Any call to that tool, any args |
| `bash.execute:pytest *` | `bash.execute` whose command string starts with `pytest ` |
| `mcp.*` | Every tool in the `mcp` namespace |
| `*` in `deny` | Blocks every tool at execute time |

Allow entries let a call skip prompting. Deny entries block it outright.

## Caveats

- **Bash patterns are loose.** `BashServer::get_permission_pattern` (`bash.cpp:200`) builds `bash.execute:<base> *`. The runtime match uses `args_to_pattern`, which takes the whole command string. `*` in `fnmatch` spans spaces and shell metacharacters, so `bash.execute:pytest *` would also match `pytest x; rm -rf ~`. The index does not show `get_permission_pattern` on the runtime match path. Deny patterns are the safer control here.
- **Persistence.** `PermissionPersister::save_permission` (`permission_persister.cpp:227`) appends an entry under `permissions.allow` or `permissions.deny` in the project YAML. It is a no-op if the entry is already present.
- **Possible issue:** the deny check happens in `execute`, after `on_tool_call` has already been fired. A denied tool may therefore show up as approved in callback and hook traces. I have not confirmed whether that matters for any consumer.