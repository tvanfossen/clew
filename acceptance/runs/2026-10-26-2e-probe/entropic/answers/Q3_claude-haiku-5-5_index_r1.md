Two lists in the `permissions:` config (`allow` and `deny`) feed a `PermissionManager`. Deny is checked in two places, and the allow list only decides whether the call skips the approval fallback. Nothing in the config decides whether a call runs by itself. The code path below is from reading the source; I did not build or run anything.

**Decision path for one tool call**

```
ToolExecutor::check_call_preconditions          src/mcp/tool_executor.cpp:667
 1. check_anti_spiral_hard_block                 (refuses first, regardless of permissions)
 2. check_schema                                 (argument validation)
 3. check_mcp_authorization                      (MCP key set, gh#/v1.9.4)
 4. check_tier_allowed                           (identity/tier allowed_tools)
 5. check_duplicate
 6. check_approval_pc -> check_approval          :161
      a. loop_config_.auto_approve_tools?  -> approved
      b. ServerManager::is_explicitly_allowed -> PermissionManager::is_allowed   (allow list)
      c. else, if callbacks_.on_tool_call set -> call it, approved = true
      d. else denied ("No approval callback — denying")
      (ON_PERMISSION_CHECK hook fires informationally)
        |
        v  (approved)
ToolExecutor -> ServerManager::execute          src/mcp/server_manager.cpp:153
 7. PermissionManager::is_denied(tool, "tool:" + first_arg)  -> deny list
      match -> "Error: Permission denied for <tool>"  (no execution)
 8. route_tool_call -> server runs the tool
```

Deny is the last gate before execution. Allow is only consulted in step 6b, and it does not override deny: a call that matches both lists passes approval and is then stopped at step 7.

**What a pattern does**

Matching is in `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`), which uses `fnmatch` with flags 0:

- Text before the first `:` is matched against the tool name. `filesystem.*` matches every tool in that namespace. `git.commit` matches exactly that tool. A pattern with no `:` matches on the tool name alone.
- Text after the `:` is matched against the call's argument pattern. The argument pattern is built by `ServerManager::args_to_pattern` (`server_manager.cpp:426`), which takes only the value of the first key in the args JSON, or `*` if there are no args or that value isn't a string. So `bash.execute:python*` matches a bash call whose first argument starts with `python`. It does not inspect other arguments.
- Patterns are checked in order. The first match wins, and the match is logged at INFO.

**Config and runtime sources**

- `config/loader.cpp:369-371` reads `permissions.allow`, `permissions.deny` and `permissions.auto_approve`.
- `auto_approve` becomes `LoopConfig::auto_approve_tools` (`facade/entropic.cpp:1489`). When it is true, step 6 approves everything. Step 7 still applies deny.
- `ServerManager::add_permission` (`server_manager.cpp:361`) adds patterns at runtime. `PermissionPersister` writes them back to the project YAML, so an "Always Allow" choice outlives the session.

**Things I noticed that you may want to check**

1. **The approval callback cannot say no.** `on_tool_call` returns `void`, and `check_approval` sets `approved = true` immediately after calling it (`tool_executor.cpp:168-173`). Any host that registers `on_tool_call` therefore approves every call that isn't on the allow list. The "callback approval" described in `permission_manager.h` is really notification-only. Auto-approve is not the only bypass.
2. **Deny with an argument constraint can fail open.** If a call's first argument is not a string, `args_to_pattern` returns `*`. A deny rule such as `bash.execute:rm*` then does not match, and the call runs. Allow rules fail closed in the same case.
3. **The header comment is inconsistent with the code.** `permission_manager.h` says unknown tools are "not denied, the engine handles prompting". In practice they are denied at step 6d unless a callback is registered (see item 1).

I did not write a test for any of these. The existing tests in `tests/unit/mcp/permission_manager_test.cpp` and `server_manager_test.cpp` would be the place to start.