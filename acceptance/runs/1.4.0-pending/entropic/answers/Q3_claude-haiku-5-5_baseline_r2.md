A tool call runs only if it clears four gates in order: a `PRE_TOOL_CALL` hook doesn't cancel it, the preconditions pass, the approval check passes, and the deny list doesn't match at execution. The allow list only skips the prompt. The deny list is the only permission-list entry that can actually stop a call, and it does so late.

## The path

```
model emits ToolCall
 └ ToolExecutor::process_single_call          tool_executor.cpp:729
   1. PRE_TOOL_CALL hook (may cancel)         :733, fire_pre_tool_hook :857
   2. check_call_preconditions                :667, in this order:
        a. anti-spiral hard block
        b. schema validation
        c. MCP key check (only if identity has a key set)   :575
        d. tier allowed_tools
        e. duplicate-call check
        f. check_approval_pc → check_approval  :161
             auto_ok = loop.auto_approve_tools
                       || ServerManager::is_explicitly_allowed  (allow list)
             if !auto_ok and on_tool_call wired → fire callback, approved = true
             if !approved → "Permission denied"
   3. execute_tool → ServerManager::execute   server_manager.cpp:153
        is_denied(deny list)? → "Error: Permission denied for X"; server never called
        else route_tool_call → in-process or external server
```

Config mapping: `permissions.{allow,deny,auto_approve}` is parsed at `src/config/loader.cpp:369-371`. `auto_approve` reaches the loop at `src/facade/entropic.cpp:1489`. The lists go into `PermissionManager` via the `ServerManager` constructor at `server_manager.cpp:35`.

## What each list does

Patterns share one matcher, `PermissionManager::pattern_matches` (`permission_manager.cpp:101`), and the same `fnmatch` call with flags 0.

- **Tool-only pattern** (`filesystem.*`, `git.commit`): the part before `:` is matched against the fully qualified tool name. With no colon, every call to that tool matches, whatever its arguments.
- **Tool plus argument pattern** (`bash.execute:pytest *`): the tool part must match, then the whole string `tool:argvalue` must match the pattern. `fnmatch` with flags 0 lets `*` cross spaces, `/`, `;` and `&&`.
- **Which argument is tested**: `ServerManager::args_to_pattern` (`server_manager.cpp:426`) uses the first key of the args object, and only if its value is a string. Otherwise it uses `*`. The nlohmann default object type is `std::map`, so "first" means alphabetically first, not the order the model wrote the arguments in. For `filesystem.write_file` with `{content, path}`, a pattern meant to restrict `path` would actually be matched against `content`. I'm relying on the nlohmann default here; I did not run it.
- **Allow list**: consulted only in `check_approval`. A match skips the prompt. It does not check the deny list.
- **Deny list**: consulted only in `ServerManager::execute`. A match blocks the call even under `auto_approve` or an allow match. A bare tool name in deny blocks that tool outright.
- **Interaction**: a call matching both lists is approved, then refused at execute. The callback has already fired by then, and the model gets an `Error: Permission denied` result rather than the standard denied message.

## Things that don't match the header comments

1. **The approval callback never denies.** `EngineCallbacks::on_tool_call` returns `void`, and `check_approval` sets `approved = true` after calling it (`tool_executor.cpp:168-173`). With a callback registered, every call not on the allow list runs unless the deny list stops it. `permission_manager.h:6-7` says tools are "approved via callback", which the code does not do. Without a callback, unlisted calls are denied.
2. **The bash-specific pattern is dead code on this path.** `BashServer::get_permission_pattern` (`bash.cpp:200`) builds `bash.execute:<base-cmd> *`, but nothing calls `ServerManager::get_permission_pattern`. Execute and allow checks use `args_to_pattern`, so the pattern is the whole command string. That makes `bash.execute:pytest *` also match `pytest -q; rm -rf ~`.
3. **"Always allow/deny" is not wired.** `PermissionPersister::save_permission` exists, but nothing in `src/` constructs it, calls `ToolExecutor::set_permission_persist`, or calls `ServerManager::add_permission`. No public C API exposes it either.