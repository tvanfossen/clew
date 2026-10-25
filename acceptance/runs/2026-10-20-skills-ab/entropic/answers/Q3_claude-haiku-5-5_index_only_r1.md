Short answer: the permission check is a chain of gates, and the allow/deny patterns only matter at one of them. I could trace most of the chain from the index, but not the exact call site that enforces the deny list, so that part is an inference.

**Order a call passes through** (`ToolExecutor::process_single_call` → `check_call_preconditions`):

```
PRE_TOOL_CALL hook ──cancel──▶ "Cancelled by hook"
  │
  ├─ anti-spiral hard block
  ├─ schema check
  ├─ MCP key authorization (identity's access level)  ──▶ denied
  ├─ tier allowed_tools (only if a tier is locked)     ──▶ denied
  ├─ duplicate call check                              ──▶ handle_duplicate
  └─ check_approval_pc → check_approval
        │
        ├─ loop_config.auto_approve_tools?  ──yes──▶ approved
        ├─ ServerManager::is_explicitly_allowed(name, args)
        │     └─ PermissionManager::is_allowed(...)   ──yes──▶ approved
        ├─ on_tool_call callback set?       ──yes──▶ approved (see caveat)
        └─ otherwise                        ──▶ "Permission denied"
  │
  ▼
ServerManager::execute → route_tool_call → server
```

**What a pattern does** (`PermissionManager::pattern_matches`, `src/mcp/permission_manager.cpp:101`):

- The pattern is split at the first `:`. The part before it is fnmatch-matched against the fully-qualified tool name (for example `filesystem.read_file`).
- With no `:`, a tool-name match is enough, so `bash.execute` allows every call to that tool.
- With a `:`, the whole pattern is fnmatch-matched against `tool:arg`. The arg is what `args_to_pattern` extracts: the value of the first string argument, or `*` if there are no args or it does not parse. So `bash.execute:pytest *` allows bash calls whose first argument starts with `pytest `.
- Lists are scanned in order and the first match wins. `is_allowed` scans `allow_list_` and `is_denied` scans `deny_list_`, each logging at INFO when it matches.
- The header documents deny as taking precedence over allow. The `is_denied` function is never called from `check_approval`, which only consults the allow list. Its only recorded caller is an ambiguous `execute` (`ast_member`), which is probably `ServerManager::execute`. I could not read that body through the index, so I cannot confirm where the deny list is enforced or whether it runs before the allow list.

**Where the lists come from:**
- `permissions.allow`, `permissions.deny` and `permissions.auto_approve` are parsed by `parse_permissions_config` (`src/config/loader.cpp:365`).
- "Always Allow/Deny" writes new patterns back to the YAML via `PermissionPersister::save_permission` (`permission_persister.cpp:227`), as `permissions.allow` or `permissions.deny` items.
- The default pattern is tool-level (`MCPServerBase::get_permission_pattern` returns the tool name). `BashServer` overrides it to finer granularity.

**Caveat to check:** in `check_approval`, if the `on_tool_call` callback is set, `approved` is forced to `true` after calling it. As written, the callback is notification only and does not decide the outcome. Without a callback, anything not explicitly allowed is denied. Confirm this is intended, since the header describes the callback as an approval step.