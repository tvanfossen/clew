**Short answer:** the call is decided by `ToolExecutor::check_approval` (`src/mcp/tool_executor.cpp:161`), with the deny list enforced later in `ServerManager::execute` (`src/mcp/server_manager.cpp:153`). The allow list only skips the prompt. The deny list is checked after approval, so it can still block a call that was approved.

**Order of events**

1. `ToolExecutor::check_call_preconditions` (`tool_executor.cpp:667`) runs first: anti-spiral hard block, schema validation, MCP authorization, tier `allowed_tools`, duplicate detection. Any of these can reject the call before permissions are consulted.
2. `check_approval_pc` (`:705`) calls `check_approval`, which computes:
   - `auto_ok = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(name, args)`. `auto_approve_tools` comes from `permissions.auto_approve` (`src/facade/entropic.cpp:1489`).
   - If not `auto_ok` and an `on_tool_call` callback is registered, it is invoked and `approved = true` unconditionally (`:168-173`). The callback is a notification, not a gate. A registered callback therefore approves everything not explicitly allowed.
   - With no callback and no allow match, the call is denied with "Permission denied".
   - A `ON_PERMISSION_CHECK` hook fires informationally either way.
3. If approved, `ServerManager::execute` (`:153`) builds `pattern = tool_name + ":" + args_to_pattern(args)` and calls `permissions_.is_denied`. A match returns `Error: Permission denied for <tool>` and the tool never runs. Otherwise it routes to an in-process server or external MCP client.

So with a callback registered, a denied tool is "approved" at step 2 and then rejected at step 3 with a different message. With no callback, it is rejected at step 2. Either way it does not run.

**What a pattern means**

Matching is in `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`) and uses `fnmatch` with flags 0. `*` also matches `/`, and there is no `**` special case.

| Pattern | Matches |
|---|---|
| `filesystem.*` | Every tool on the `filesystem` server, any args |
| `git.commit` | That tool name, any args (no colon means no arg check) |
| `bash.execute:python*` | `bash.execute` whose first string arg starts with `python` |
| `bash.execute:rm *` | `bash.execute` whose command starts with `rm ` |

The arg part is checked against only the **first string-valued argument** (`args_to_pattern`, `server_manager.cpp:426`). Empty args or non-string first args become `*`. So an arg pattern on `path` will be checked against whichever argument is first.

**Lists and precedence**

- `permissions.allow` and `permissions.deny` are loaded from YAML (`src/config/loader.cpp:369-370`).
- Deny is checked in `execute`, so it wins over allow, as the header states (`permission_manager.h:7`).
- "Always allow/deny" choices are persisted by `PermissionPersister` to these lists (`src/storage/permission_persister.cpp:232`).

**Gotcha I found:** the "Always allow" pattern generated for bash is `bash.execute:<base> *` (`src/mcp/servers/bash.cpp:213`). Because the literal space is required, that pattern does not match a bare command with no arguments. A persisted `bash.execute:ls *` will not cover a plain `ls` call, which then gets prompted again. I inferred this from fnmatch semantics and did not run it.

I did not trace the YAML loader beyond the `allow`/`deny` keys, or the external-MCP path beyond `route_external_call`.