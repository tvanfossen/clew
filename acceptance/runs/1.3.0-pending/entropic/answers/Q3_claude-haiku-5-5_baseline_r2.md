## Short answer

The call runs only if it clears three gates in order: a pre-tool hook, the precondition chain (which includes the approval check), and a deny check at dispatch. The allow list only skips the approval step. It never overrides deny, schema, or tier checks. In this tree, though, the interactive prompt path looks unwired, so a call that matches no allow pattern is refused unless `auto_approve` is set.

## Flow for one call

```
process_single_call          tool_executor.cpp:729
 ├─ PRE_TOOL hook            → "Cancelled by hook" if it returns true
 ├─ check_call_preconditions tool_executor.cpp:667
 │   ├─ anti-spiral hard block
 │   ├─ check_schema         (args vs. JSON schema)
 │   ├─ MCP authorization
 │   ├─ tier allowed_tools   (gh#83, dispatch-time)
 │   ├─ duplicate-call check
 │   └─ check_approval_pc → check_approval (tool_executor.cpp:161)
 │        approved = auto_approve || is_explicitly_allowed(allow list)
 │        if !approved and on_tool_call set → approved = true (notify only)
 │        else → "Permission denied"
 └─ ServerManager::execute   server_manager.cpp:153
     ├─ is_denied(deny list) → "Error: Permission denied for <tool>"
     └─ route to in-process server, or external MCP client
```

Three details matter here:

- **Deny is the last gate.** It is checked in `ServerManager::execute`, after approval. `check_approval` only consults the allow list. So a call that matches both lists, or runs under `auto_approve`, is still refused at dispatch.
- **`on_tool_call` looks unwired.** `callbacks_.on_tool_call` is the only route to "approved" besides the allow list and `auto_approve`. I found no assignment to it anywhere under `src/` (tests excluded). If it is really null, every non-allowed call is denied with "No approval callback — denying". Please check the C facade before relying on this.
- **Even when the callback is set, it does not wait.** The code calls it and then sets `approved = true` unconditionally. Nothing blocks on a user answer in this path.

## What a pattern does

Patterns are `tool[:argpattern]`, split at the first `:`, and both halves use `fnmatch` with no flags. Config is `permissions: { allow: [...], deny: [...], auto_approve: bool }` (`config.h:589`, `loader.cpp:365`).

- **Tool part** (before the colon) is matched against the fully qualified tool name. `filesystem.*` covers every filesystem tool. `git.commit` matches exactly one.
- **No colon:** the tool-name match is enough, so the pattern covers every call to that tool.
- **With a colon:** the whole pattern is matched against `tool_name:<arg>`, where `<arg>` comes from `args_to_pattern` (`server_manager.cpp:426`). That function takes the first key of the args object and uses its value if it is a string. Otherwise it uses `*`.
- **Deny patterns use the same matching**, and the first match wins.

Two consequences:

- **The argument is chosen by sort order, not by position.** nlohmann objects iterate in key order, so `write_file` with `{content, path}` would match against `content`, not `path`. I did not run this, so treat it as a reading of the code until tested.
- **`*` crosses shell metacharacters.** `bash.execute:python*` matches `python x && rm -rf ~`. The bash server's own helper (`bash.cpp:200`, which produces `bash.execute:<base> *`) is not called on this path. `ServerManager::get_permission_pattern` has no callers, so the check above is the only one that runs.

## Dead or unwired pieces

- `set_permission_persist` stores the callback, but nothing calls `permission_persist_`. `PermissionPersister::save_permission` has no callers in `src/`. "Always allow" therefore does not persist.
- `ServerManager::add_permission` has no callers in `src/` either, so runtime grants are not created from anywhere in the source.