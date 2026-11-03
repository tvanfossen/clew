## Short answer

In this codebase, the permission config does not decide much on its own. A frontend callback approves every call that reaches it, because `check_approval` ignores the callback's result. The deny list is the only hard block. The allow list only suppresses the callback. Separately, the matcher is weaker than the header comments suggest.

## The path a tool call takes

```
model emits tool call
  │
  ▼
ToolExecutor::check_call_preconditions          tool_executor.cpp:667
  1. anti-spiral hard block
  2. schema validation (check_schema)
  3. MCP key check (check_mcp_authorization)    only if identity has a key set
  4. tier allowed_tools (check_tier_allowed)
  5. duplicate-call check
  6. check_approval_pc → check_approval         tool_executor.cpp:161
        auto_ok = auto_approve_tools || is_explicitly_allowed(allow list)
        if !auto_ok and on_tool_call set → call callback, approved = true
        else → approved = auto_ok (false → "Permission denied")
  │
  ▼
ServerManager::execute                          server_manager.cpp:153
  if is_denied(deny list) → "Error: Permission denied", tool NOT run
  │
  ▼
route_tool_call → in-process server or external MCP client
```

Each layer runs in order, and the first rejection stops the call.

## What each list does

**`permissions.allow`** (`PermissionManager::is_allowed`, `permission_manager.cpp:59`)
- A match makes `check_approval` return true without invoking the frontend callback.
- With no callback wired, it is the only per-pattern way to run a call. Otherwise a call is denied unless `auto_approve` is set.
- It does not bypass the deny list. Deny is checked later, in `execute`.

**`permissions.deny`** (`PermissionManager::is_denied`, `permission_manager.cpp:38`)
- Any single match blocks the call at `ServerManager::execute`, after approval has already run.
- Because it runs after approval, a frontend can be prompted for a call that is then denied.
- `auto_approve: true` does not override it.

**`permissions.auto_approve`** (`config.h:592`, `tool_executor.cpp:163`)
- Skips the callback and approves everything that passes the earlier preconditions.

## Pattern syntax

Source: `pattern_matches`, `permission_manager.cpp:101`.

- The text before the first `:` is matched against the tool name with `fnmatch`. Example: `filesystem.*` matches all filesystem tools.
- With no `:`, a match on the tool name is enough.
- With a `:`, the full pattern is then matched against `tool:<argument>`. The argument comes from `args_to_pattern` (`server_manager.cpp:426`): the value of the first JSON key, only if it is a string. Otherwise it is `*`.
- `fnmatch` is called with flags 0, so `*` also matches `/` and spaces.

Example: `bash.execute:pytest *` is evaluated against the whole command string. It matches `pytest -x` and also `pytest; rm -rf ~`, because no shell parsing happens. That is a bypass for any allow rule with a trailing `*`.

## Things that differ from the docs

1. **The callback cannot deny.** The signature is `void (*on_tool_call)(const char*, void*)` (`engine_types.h:370`). `check_approval` sets `approved = true` after calling it. A frontend can only observe the request, not refuse it. Denial has to come from the deny list or the earlier preconditions.
2. **The bash base-command pattern is never used by the gate.** `BashServer::get_permission_pattern` builds `bash.execute:<base> *` (`bash.cpp:213`), but `ServerManager::get_permission_pattern` has no callers in `src/`. The gate uses `args_to_pattern`, which matches the full command.
3. **`PermissionPersister::save_permission` has no call site in `src/`.** Nothing in the library writes "always allow" patterns back to config.
4. **The MCP key layer is separate.** `MCPAuthorizationManager` only enforces for identities that have a registered key set. Unregistered identities pass (`mcp_authorization.cpp:94`).

I did not run the test suite. These conclusions come from reading the code paths above.