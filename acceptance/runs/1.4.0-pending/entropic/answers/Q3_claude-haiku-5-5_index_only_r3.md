**Short answer:** a call runs only if it clears two gates, one before dispatch and one inside `ServerManager::execute`. The allow and deny lists are fnmatch patterns, and deny always wins. I traced this from the index without opening source, so the flow below is from the function bodies it returned.

**Flow**

```
tool call
 └─ ToolExecutor::process_single_call
     ├─ PRE_TOOL_CALL hook            → may cancel ("Cancelled by hook")
     ├─ check_call_preconditions
     │   └─ check_approval_pc         → check_approval → "Permission denied" if false
     ├─ execute_tool
     │   └─ ServerManager::execute
     │       ├─ is_denied(tool, "tool:argpat")   → "Permission denied for <tool>" if match
     │       └─ route_tool_call → MCP server
     └─ finalize + POST_TOOL_CALL hook
```

**Gate 1: approval (`ToolExecutor::check_approval`, `src/mcp/tool_executor.cpp:161`)**

1. `loop_config_.auto_approve_tools` is true → approved. This comes from `permissions.auto_approve` via `build_loop_config` (`src/facade/entropic.cpp:1489`).
2. Otherwise `ServerManager::is_explicitly_allowed` builds `tool:<first arg value or *>` and calls `PermissionManager::is_allowed`, which returns true on the first allow pattern that matches.
3. Otherwise, if an `on_tool_call` callback is registered, the callback fires and `approved` is set to true anyway. Its return value is not read.
4. The ON_PERMISSION_CHECK hook fires informationally. If nothing approved the call, it is denied with a warning.

**Gate 2: deny (`ServerManager::execute`, `src/mcp/server_manager.cpp:153`)**

This runs after approval and checks deny even for calls that were auto-approved or allow-listed. A matching deny pattern blocks the call and returns a JSON error envelope. Deny is therefore absolute: an allow entry cannot override it, though the header's "deny takes precedence" comment is only true because of this ordering.

**What a pattern does**

- A pattern is split at the first `:`.
- The part before the colon is fnmatch-matched against the fully-qualified tool name (e.g. `bash.execute`).
- If there is no colon, a tool-name match is enough, so `filesystem.read_file` allows or denies every call to that tool.
- If there is a colon, the part after it is fnmatch-matched against `tool:<argument>`. Shell-style globs apply, and `*` crosses `/` because no FNM_PATHNAME flag is set.
- The argument compared is the first string-valued field of the call's JSON arguments (`args_to_pattern`). If there are no arguments, or parsing fails, it is `*`.
- For the Bash server, `get_permission_pattern` generates the "Always Allow/Deny" pattern as `execute:<base command> *`. The base command is the text before the first space, so `execute:git *` covers `git status` and `git push`.
- `add_permission(pattern, allow)` adds a pattern at runtime and de-duplicates it. The persister writes it into the project YAML under `permissions.allow` or `permissions.deny`, and the loader reads those lists plus `auto_approve`.

**Concerns I'd flag**

- Step 3 above looks like a real bug. `check_approval` returns true whenever a callback is registered, whatever the callback decides, because its return value is ignored. A consumer who registers `on_tool_call` as a "prompt the user" hook gets an automatic approval instead. I read this from the body, but I did not run it or check the callback's type.
- `check_dup_or_approval` has no callers in the index. The live path appears to be `check_approval_pc`, so that function may be dead code, but I have not confirmed it.