The index answers this from code bodies and the header docs. I did not re-read the source files, and I could not view the body of `ServerManager::execute` directly, so its deny check is inferred from the call graph (see the caveat below).

## What decides whether a call runs

Two layers decide, in order. The first is `ToolExecutor`, which decides whether the user or config approved the call. The second is `ServerManager`, which applies the deny list and routes the call.

```
tool call
  │
  ▼
ToolExecutor::check_call_preconditions            (tool_executor.cpp:667)
  1. anti-spiral hard block
  2. check_schema                  → rejected_schema
  3. check_mcp_authorization       → rejected_precondition
  4. check_tier_allowed            → rejected_unauthorized
  5. check_duplicate               → rejected_duplicate
  6. check_approval_pc → check_approval        (tool_executor.cpp:161)
        approved = auto_approve_tools
                || ServerManager::is_explicitly_allowed(name, args)
        if !approved and callbacks.on_tool_call != nullptr → approved = true
        if !approved → "Permission denied"
  │
  ▼
ToolExecutor::execute_tool                        (tool_executor.cpp:379)
  │
  ▼
ServerManager::execute(name, args)                (server_manager.h:113)
  - checks deny list via PermissionManager::is_denied   (inferred, see caveat)
  - route_tool_call → in-process server or external client
```

Points that matter:

- **Allow list = skip the prompt.** `is_explicitly_allowed` is the only path to approval without a callback. It builds `tool:first_arg` and checks `PermissionManager::is_allowed`.
- **Deny is a second gate.** `is_denied` is called from `ServerManager::execute`, which is downstream of approval. So a deny match should block the call even when `auto_approve_tools` or an allow match approved it. The header says "Deny list takes precedence over allow list." That is consistent with the call graph, but I could not confirm the order in the body.
- **Surprising behavior in `check_approval`.** If `on_tool_call` is non-null, `approved` is set to `true` unconditionally. The callback reads as an approval prompt, but as written it is a notification and always approves. Whether the host treats it as a gate depends on what the host's callback does. Worth checking in the frontend code. The log line "No approval callback — denying" only fires when no callback is registered.
- **Not interactive here.** Nothing in the index shows the callback blocking for a user answer.

## What a pattern does

Patterns are `fnmatch` strings in `permissions.allow` / `permissions.deny` (`PermissionsConfig`, config.h:589). `pattern_matches` (permission_manager.cpp:101) works like this:

- Split the pattern at the first `:`.
- The part before the colon is matched against the fully-qualified tool name, for example `filesystem.read_file`. Globs such as `filesystem.*` work.
- With no colon, the tool-name match alone is sufficient, so the pattern covers every argument set.
- With a colon, the full string `tool:arg` must also match. The arg is built by `args_to_pattern`, which takes the first JSON argument's string value, or `*` if there are no args or the parse fails. Only the first argument is considered.

`get_permission_pattern` (server_base.h:87) produces the pattern for "Always Allow/Deny". The default returns the bare tool name, so it covers every call to that tool. The bash server overrides it to `execute:{base_cmd} *`, which is per-command granularity.

Persistence: `PermissionPersister` appends patterns to `permissions.allow` / `deny` in `.entropic/config.local.yaml` (read-modify-write, mutex-guarded). Runtime additions go through `add_permission`.

## Caveats

- `ServerManager::execute` is not directly queryable. Its deny placement rests on the `execute → is_denied` edge and its doc comment ("Checks permissions before execution"). Confirm the ordering against its body.
- The default is deny (`docs/architecture-cpp.md`). The `PermissionManager` constructor takes its lists directly, so the default-deny behavior comes from the approval path rather than from a default deny list.