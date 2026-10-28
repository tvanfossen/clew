**What decides whether a call runs:** the deny list is the only hard block. The allow list only skips the approval step. With an approval callback registered, approval always succeeds, so the callback is a notification, not a gate.

**Flow for one tool call** (`ToolExecutor::process_single_call`, `src/mcp/tool_executor.cpp`):

1. **PRE_TOOL_CALL hook.** If it returns true, the call is cancelled ("Cancelled by hook").
2. **Preconditions.** Duplicate detection runs first, then approval (`check_dup_or_approval` / `check_approval_pc`).
3. **Approval** (`ToolExecutor::check_approval`). The call is approved if either:
   - `loop_config_.auto_approve_tools` is set, or
   - `ServerManager::is_explicitly_allowed()` matches an allow pattern.

   If neither holds and `callbacks_.on_tool_call` is set, the call is approved anyway. `on_tool_call` returns `void` (`engine_types.h:370`), so the host cannot refuse here. If there is no callback, the call is denied with "Permission denied".
4. **Deny check** (`ServerManager::execute`, `src/mcp/server_manager.cpp:153`). `PermissionManager::is_denied()` runs on the call. A match returns an error envelope and the call never reaches a server. This runs after approval, so a deny beats an allow.
5. **Route** to the owning MCP server (`route_tool_call`).

**What a pattern means** (`PermissionManager::pattern_matches`, `src/mcp/permission_manager.cpp:101`):

| Entry form | Matches when |
|---|---|
| `filesystem.*` (no `:`) | the fully-qualified tool name matches the fnmatch glob, whatever the args |
| `bash.execute:python*` | the tool part matches **and** `tool:<arg>` matches the glob |

- The text before the first `:` is the tool glob. The text after it is an argument glob.
- The argument value comes from `ServerManager::args_to_pattern()`. It takes the first key of the args JSON object, and only if that value is a string. Otherwise it uses `*`.
- Matching is plain `fnmatch` with flags 0. `*` also matches `/`, and no paths are normalized.
- Lists are checked in order and the first match wins. Deny is checked in `execute`, not in `is_allowed`.

**Consequences:**

- **Deny-by-arg is fragile.** `args_to_pattern` uses the first key in the JSON object. nlohmann objects are ordered maps, so that is the alphabetically first key, not necessarily the command the model wrote. A deny like `bash.execute:rm*` depends on that key being `command` and sorting first. If the first key is non-string, the pattern becomes `*` and the arg-level deny never matches. I did not confirm the bash tool's argument schema, so treat this as a probable hole to check.
- **`BashServer::get_permission_pattern`** builds `bash.execute:<base_cmd> *`. The index shows matching uses `args_to_pattern`, not this method. I read this method as the string offered for "Always Allow/Deny" and persisted by `PermissionPersister` into `permissions.allow` / `permissions.deny` in YAML. The index's call edges for it are sparse, so confirm before relying on it.
- **`auto_approve_tools` skips approval only.** Deny patterns still apply.

**The gap:** the header (`permission_manager.h:6-7`) and `docs/architecture-cpp.md:517` say tools "must be explicitly allowed or approved via callback" under default-deny. The code does the opposite: with any `on_tool_call` callback set, unlisted tools run unless a deny pattern matches. I did not run this, so it is a read of the code. The fix would be to make the callback return a verdict, or to change the docs to say default-allow.