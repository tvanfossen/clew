The short answer: a call runs only if it clears a fixed sequence of gates in `ToolExecutor`, and the permission lists are consulted at one of those gates. Two things I could not confirm from the index are called out at the end.

**Gate order** (`ToolExecutor::process_single_call`, `src/mcp/tool_executor.cpp:729`)

```
PRE_TOOL_CALL hook ──cancel?──► "Cancelled by hook"
  └─ check_call_preconditions (line 667)
       1. anti-spiral hard block   → rejected_anti_spiral
       2. schema check             → rejected_schema
       3. MCP authorization        → rejected_precondition
       4. tier allowed_tools       → rejected_unauthorized
       5. duplicate-call check     → rejected_duplicate
       6. check_approval_pc        → "Permission denied"
  └─ execute_tool → finalize → POST_TOOL_CALL hook
```

The pre-hook fires before any of these and can cancel the call outright. The permission lists are only read in step 6.

**How step 6 decides** (`check_approval`, `src/mcp/tool_executor.cpp:161`)

1. `auto_ok` is true if `loop_config_.auto_approve_tools` is set, or if `ServerManager::is_explicitly_allowed` matches.
2. If not `auto_ok` and an `on_tool_call` callback is registered, the call is approved anyway. The callback is only a notification, so it is not a gate.
3. `ON_PERMISSION_CHECK` fires as informational.
4. With no callback and no allow match, the call is denied.

`is_explicitly_allowed` (`src/mcp/server_manager.cpp:286`) builds the pattern `tool_name + ":" + args_to_pattern(args)` and calls `PermissionManager::is_allowed`. It only checks the allow list.

**What a pattern means** (`PermissionManager::pattern_matches`, `src/mcp/permission_manager.cpp:101`)

- The text before the first `:` is an fnmatch glob matched against the fully qualified tool name, e.g. `filesystem.*`.
- If there is no `:`, a tool-name match is enough, so the pattern covers every call to that tool.
- If there is a `:`, the full `tool:argpattern` string must also match, again via fnmatch.
- `args_to_pattern` uses the first string-valued argument of the call. Empty or `{}` args become `*`.
- The default `MCPServerBase::get_permission_pattern` returns the bare tool name, so it is tool-level. `BashServer` overrides it for finer grain (for example `bash.execute:pytest *`). I did not read the override body.

**Where the lists come from**

- Config: `permissions:` with `allow`, `deny` and `auto_approve` (`PermissionsConfig`, `include/entropic/types/config.h:589`; parsed in `parse_permissions_config`, `src/config/loader.cpp:365`).
- Runtime: `PermissionManager::add_permission` (`include/entropic/mcp/permission_manager.h:71`).
- "Always Allow/Deny" from the UI: `PermissionPersister::save_permission` (`src/storage/permission_persister.cpp:227`) writes the pattern into `config.local.yaml` under `permissions.allow` or `permissions.deny`, deduplicating first.

**Deny semantics**

- The header says the deny list takes precedence over the allow list, and `is_denied` returns true on any deny match.
- Per the index, `is_denied` is called from a function named `execute` in `ServerManager`. That is the dispatch-side check, not from `check_approval`.

**What I could not settle from the index**

- The body of the `ServerManager` caller of `is_denied` is not resolvable by name, so I cannot confirm the exact order of deny versus `auto_approve` or whether a deny hit can be bypassed when `auto_approve` is true.
- `check_approval` as written approves any call when a callback is registered, regardless of the lists. Whether a deny match still blocks such a call depends on that unread dispatch-side check. If that check is absent, a registered callback would bypass deny entirely. Reading `ServerManager`'s execute path would settle it.