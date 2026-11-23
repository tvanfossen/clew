**Short answer:** the call runs only if it clears an ordered gauntlet in `ToolExecutor`, and the permission lists are consulted at two separate points. The allow list decides whether the user is prompted. The deny list is enforced later, in `ServerManager::execute`.

**Decision order** (`process_single_call`, `src/mcp/tool_executor.cpp:729`)

```
PRE_TOOL_CALL hook ──cancel?──► denied ("Cancelled by hook")
  │
check_call_preconditions (tool_executor.cpp:667)
  1. anti-spiral hard block
  2. schema check
  3. MCP authorization
  4. tier allowed
  5. duplicate-call check
  6. check_approval_pc → check_approval (:161)
        approved = loop auto-approve OR is_explicitly_allowed(allow list)
        if not approved and an on_tool_call callback exists → approved = true
        if still not approved → "Permission denied"
  │
execute_tool → ServerManager::execute (server_manager.cpp:153)
  pattern = tool + ":" + args_to_pattern(args)
  if is_denied(pattern) → "Error: Permission denied"   ◄── deny list wins here
  else route_tool_call
```

**What a pattern does**

- Patterns are `tool` or `tool:argpattern`, matched by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`) with `fnmatch`, flags 0.
- Tool-only pattern (`filesystem.*`): matches on the tool name alone, for any arguments.
- `tool:argpattern` (`execute:ls *`): the tool part must match, then the full `tool:arg` string must match. The argument value comes from `args_to_pattern`, which takes the first JSON key's string value, or `*` when there is none. Key order follows the JSON object's iteration order, not the order the arguments were written in.
- Allow matches return `true` from `is_allowed`, which skips the prompt. Deny matches return `true` from `is_denied`, which blocks the call. Deny is checked first in `execute`, so it overrides an allow.

**Things that stood out**

1. **Callback path is not a gate.** In `check_approval`, if no allow-list or auto-approve match exists and an `on_tool_call` callback is registered, `approved` is set to `true` after the callback fires. The callback's return value is ignored (it returns void). Under this reading, the callback only notifies, and the deny list is the only thing left that can stop an unlisted call. I read this from the body and did not test it.
2. **Bash patterns are prefix-style globs.** `BashServer::get_permission_pattern` (`bash.cpp:200`) produces `execute:<base_cmd> *`. Matching uses `fnmatch` without `FNM_PATHNAME`, so `*` also matches `;`, `|` and `&&`. An allow of `execute:ls *` would therefore match `ls; rm -rf /`. Because the bash pattern generator and the matching argument (`args_to_pattern`) are not the same string, I'd test this before relying on it.
3. **"Always Allow/Deny" writes to project YAML.** `PermissionPersister` (`src/storage/permission_persister.cpp`) appends patterns to `permissions.allow` / `permissions.deny` using line-based edits. Config parsing is `parse_permissions_config` (`src/config/loader.cpp:365`), which reads `allow`, `deny` and `auto_approve`.

**Not verified:** how `permissions.auto_approve` in config reaches `loop_config_.auto_approve_tools`, and the exact behaviour of `ServerManager::is_explicitly_allowed` for servers that override `get_permission_pattern`. The index did not return the code for either.