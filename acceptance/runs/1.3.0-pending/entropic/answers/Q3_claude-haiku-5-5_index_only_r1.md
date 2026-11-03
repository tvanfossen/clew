**Short answer:** two gates decide whether a call runs. The first, in `ToolExecutor::check_approval`, decides whether the call may proceed at all. The second, in `ServerManager::execute`, applies the deny list just before routing. Deny patterns are not checked at the first gate, so a deny pattern only bites at the second.

```
model emits tool call
  │
  ▼
ToolExecutor::check_approval            (src/mcp/tool_executor.cpp:161)
  approved = loop.auto_approve_tools
          || ServerManager::is_explicitly_allowed(name, args)   → PermissionManager::is_allowed
  if !approved and on_tool_call callback set → callback fires, approved = true
  if !approved → "No approval callback — denying", return false
  │
  ▼  (approved)
ServerManager::execute                  (src/mcp/server_manager.cpp:153)
  pattern = name + ":" + args_to_pattern(args)
  if PermissionManager::is_denied(name, pattern) → {"result":"Error: Permission denied for …"}
  │
  ▼
route_tool_call → server runs
```

**Gate 1 (`check_approval`)**
- `auto_approve_tools` in the loop config skips the lists entirely. It does not skip the deny check in gate 2.
- Otherwise the call must match an allow pattern through `is_allowed`, which is the explicit skip-prompt path.
- If nothing matches and a callback is wired, the callback is invoked and the call is then marked approved. The return value of the callback is never read. The header says tools are "approved via callback," but the code approves unconditionally once the callback is present. I'd treat that as a likely defect to verify, since it means the callback is a notification rather than a gate.
- With no allow match and no callback, the call is denied (default-deny).

**Gate 2 (`ServerManager::execute`)**
- Deny is checked here, after approval. Deny wins over allow and over `auto_approve`, because an allow match alone never reaches the server.
- The denial is returned as a normal tool result (an error string), not as an exception.

**What a pattern means** (`PermissionManager::pattern_matches`, `src/mcp/permission_manager.cpp:101`)
- The pattern is split at the first `:`. The left part is matched with `fnmatch` against the fully qualified tool name, e.g. `filesystem.*` matches all filesystem tools.
- A pattern with no `:` matches that tool regardless of arguments. `git.commit` allows every git commit.
- A pattern with a `:` also has its right part matched against the call's pattern string, `name:<first-arg>`. That string comes from `args_to_pattern`: the value of the first string-valued argument, or `*` if there are no args or parsing fails. So `bash.execute:python*` matches bash calls whose first argument starts with `python`.
- `fnmatch` is called with flags 0, so `*` also crosses `/` and other separators. `filesystem.*:/etc*` is a broader pattern than it looks.
- Matching is glob-based, so `*` can match a separator. The `:` split is literal, so a tool name containing `:` cannot be expressed.

**Lists and config**
- `PermissionsConfig` has `allow`, `deny` (glob string lists) and `auto_approve` (bool), parsed by `parse_permissions_config` (`src/config/loader.cpp:365`).
- `PermissionManager` holds the two lists. Each list is checked in order and any single match is enough.
- `BashServer::get_permission_pattern` produces `bash.execute:<base-cmd> *`, for example `bash.execute:git *`. That is the form the "Always Allow/Deny" suggestion uses. The base server default is tool-level only. The gate-2 code path uses `args_to_pattern`, not this override, so I could not confirm from the index how a bash allow such as `bash.execute:git *` lines up with the first-argument pattern built at gate 2.

**Not settled by the index**
- Where `check_approval` sits relative to the duplicate and circuit-breaker checks (`check_dup_or_approval`, `check_approval_pc`).
- How the `PermissionManager` lists are populated from config, and how `PermissionPersister` writes "Always" choices back to the project YAML.
- The `ToolExecutor` header also mentions tier allowlists and `bash_commands` restrictions. I did not trace those.