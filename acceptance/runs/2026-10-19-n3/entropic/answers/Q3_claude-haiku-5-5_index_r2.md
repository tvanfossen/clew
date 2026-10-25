The short answer: the **deny list is the only list enforced at the point of execution**, the **allow list only skips the prompt**, and the **approval callback cannot refuse anything**. That last point contradicts the header comment, so treat it as a likely bug.

## Decision path

```
tool call from model
  │
  ▼
ToolExecutor::check_call_preconditions          src/mcp/tool_executor.cpp:667
  1. anti-spiral hard block
  2. check_schema              (argument validation)
  3. check_mcp_authorization
  4. check_tier_allowed
  5. check_duplicate
  6. check_approval_pc → check_approval         tool_executor.cpp:161
        auto_ok = loop_config_.auto_approve_tools
                  || server_manager_.is_explicitly_allowed(name, args)
        if !auto_ok and on_tool_call set → call it, approved = true   ← no veto
        if !approved → "Permission denied" rejection
  │ (passes)
  ▼
ServerManager::execute                          server_manager.cpp:153
  pattern = name + ":" + args_to_pattern(args)
  if permissions_.is_denied(name, pattern) → "Permission denied" result
  │ (passes)
  ▼
route_tool_call → server
```

Checks 2 to 4 and the approval step all sit before execution, and the deny check sits inside `ServerManager::execute`, after approval has already happened.

## What each list does

Both lists come from the `permissions` config section (`PermissionsConfig`, loaded in `src/config/loader.cpp`). Each entry is a pattern of the form `tool` or `tool:argpattern`, matched by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`):

- **Split at the first `:`.** The left side is `fnmatch`ed against the fully-qualified tool name, for example `bash.execute`.
- **No colon** (`filesystem.*`, `git.commit`): a tool-level match. Every call to that tool matches, whatever its arguments.
- **With a colon** (`bash.execute:python*`): the right side is `fnmatch`ed against `tool:firstArgValue`. `args_to_pattern` takes the first string value of the JSON args, or `*` when there are none. So `bash.execute:python*` matches a bash call whose command starts with `python`.
- **`allow`** (`is_allowed`, line 59): a match means the call skips the prompt. It does not run anything by itself. The call still goes through the other preconditions.
- **`deny`** (`is_denied`, line 38): a match blocks the call at `ServerManager::execute`. Nothing overrides it, and `auto_approve_tools` does not bypass it.

Patterns are generated for "Always Allow/Deny" choices by `get_permission_pattern`. The base class returns the bare tool name (`server_base.cpp:87`). `BashServer` overrides it to `bash.execute:{base_cmd} *` (`bash.cpp:200`). `PermissionPersister` writes those patterns back into the project YAML.

## Points that need a decision

1. **The approval callback cannot deny.** `on_tool_call` is `void (*)(const char*, void*)` (`engine_types.h:370`), so `check_approval` sets `approved = true` whenever a callback exists. The header says tools are "approved via callback", and the `check_approval` comment says "true if approved". The code does neither. Any call that misses the allow list is approved if a callback is registered, and only deny-list entries stop it, one step later.
2. **Deny rules are not checked during approval.** A denied tool with a callback registered still gets prompted, then fails in `execute`. The user is asked about calls that are already blocked.
3. **I did not confirm the call site** of `ServerManager::execute` from the tool executor. The chain above assumes the approved path reaches it, which the file layout implies but I did not read.

Pinning down point 1 would need an experiment: register a callback with an empty allow list and confirm a non-allowed bash call still runs. I have not run it.