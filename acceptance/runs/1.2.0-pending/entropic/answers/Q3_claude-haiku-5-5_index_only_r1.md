The decision runs in two places: `ToolExecutor` decides whether the call is approved, and `ServerManager::execute` decides whether a denied call is dropped. The deny list is only checked in the second.

```
tool call
 └─ ToolExecutor::process_single_call
     ├─ PRE_TOOL_CALL hook: may cancel
     └─ check_call_preconditions, in order:
         1. anti-spiral hard block
         2. schema check
         3. MCP authorization
         4. tier check
         5. duplicate check
         6. check_approval_pc → check_approval
             ├─ auto_approve_tools  OR  is_explicitly_allowed(allow list)  → approved
             ├─ else, if on_tool_call callback is set                      → approved = true
             └─ else                                                       → denied
     └─ execute_tool → ServerManager::execute
         ├─ is_denied(deny list)  → "Permission denied" JSON, call never routed
         └─ route_tool_call       → server runs
```

**What each list does**

- **`allow`** is consulted in `check_approval` through `is_explicitly_allowed`. A match skips the approval prompt. It does not override the deny list, because `execute` checks deny afterward.
- **`deny`** is consulted only in `ServerManager::execute`, after approval. A match blocks the call, even if the allow list or `auto_approve` already approved it.
- **`auto_approve`** (`PermissionsConfig`, `include/entropic/types/config.h:592`) skips the allow check. Deny still applies. I did not confirm that this config field is the same one `check_approval` reads as `loop_config_.auto_approve_tools`.

**How a pattern matches** (`PermissionManager::pattern_matches`, `src/mcp/permission_manager.cpp:101`)

- The pattern is split at the first `:`. The left side is fnmatch-ed against the fully-qualified tool name, for example `filesystem.*` or `git.commit`.
- With no `:`, the tool-name match is enough, so the pattern covers every argument set for that tool.
- With a `:`, the right side is fnmatch-ed against `tool:<first string argument>`. `ServerManager::args_to_pattern` takes the first string value of the arguments, and returns `*` when there is none.
- Matching uses `fnmatch` with flags 0, so `*` also crosses `/` and `:`.
- Example: `bash.execute:git *` matches a bash call whose first argument starts with `git `.
- `BashServer::get_permission_pattern` builds the pattern written by "Always Allow" as `tool:base_cmd *`. The matching step compares against the full first argument, so that pattern still matches a command like `git status -s`.
- Deny patterns use the same matcher.

**Two things in the code I'd flag**

1. **The approval callback cannot deny.** `EngineCallbacks::on_tool_call` is declared `void(*)(const char*, void*)` (`include/entropic/core/engine_types.h:370`). In `check_approval`, if the callback is set, the code calls it and then sets `approved = true` without checking anything. So with a callback registered, any call not on the allow list is approved, and the only gate left is the deny list. The header comment for `permission_manager.h` describes a default-deny model where tools "must be explicitly allowed or approved via callback". That matches the no-callback path only. I read this from the index without running it, so a test would confirm it.
2. **Deny is a second check, not a precondition.** A denied call still goes through approval first and only fails in `execute`. If an approval hook or a logging hook fires in between, it sees the call as approved. The `ON_PERMISSION_CHECK` hook reports `allowed` based on the approval result, so it can report `allowed` for a call the deny list then blocks.

Config is loaded from the `permissions` section by `parse_permissions_config` (`src/config/loader.cpp:365`), which reads `allow`, `deny` and `auto_approve`. "Always Allow/Deny" writes new patterns back to project config through `PermissionPersister`. I did not trace the persister's write path in depth.