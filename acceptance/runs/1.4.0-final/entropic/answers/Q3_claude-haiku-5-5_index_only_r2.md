The index answers this from the code bodies. I did not run anything, so the behaviour below is what the source says, not something I observed at runtime.

**What decides whether a call runs**

Three checks run in sequence, and the deny list is the only one that can stop a call after the approval step.

```
tool call
 │
 ├─ 1. PRE_TOOL_CALL hook               → may cancel ("Cancelled by hook")
 ├─ 2. preconditions (check_call_preconditions)
 │     anti-spiral block → schema → MCP authorization → tier → duplicate
 │     └─ 3. check_approval (check_approval_pc)
 │          approved = auto_approve_tools
 │                     OR allow-list match on "tool:first-arg"
 │          if not approved and on_tool_call callback set → approved = true
 │          if not approved and no callback              → "Permission denied"
 │          fires ON_PERMISSION_CHECK (informational)
 └─ 4. ServerManager::execute
       deny-list match on "tool:first-arg" → error JSON "Permission denied for …"
       else route_tool_call → server runs the tool
```

- **Step 3** is `ToolExecutor::check_approval` (`src/mcp/tool_executor.cpp`, lines 161–188). It asks `ServerManager::is_explicitly_allowed`, which builds the pattern and calls `PermissionManager::is_allowed`.
- **Step 4** is `ServerManager::execute` (`src/mcp/server_manager.cpp`, lines 153–168). This is the only place the deny list is consulted.
- **Config** comes from `PermissionsConfig` (`include/entropic/types/config.h:589`): `allow`, `deny`, and `auto_approve`, parsed by `parse_permissions_config` in `src/config/loader.cpp`.
- **"Always Allow/Deny"** writes through `PermissionPersister::save_permission`, which inserts `- <pattern>` under `permissions.allow` or `permissions.deny` in the project YAML.

**What a pattern in each list does**

- Form is `tool` or `tool:args`. `pattern_matches` splits on the first colon.
- The tool part is matched with `fnmatch` against the fully-qualified tool name. So `filesystem.*` covers every filesystem tool.
- A pattern with no colon matches that tool with any arguments.
- A pattern with a colon also has its full string matched against `tool:argvalue`, where `argvalue` is the first string-valued argument (`ServerManager::args_to_pattern`). Empty args, `{}`, or unparseable JSON become `*`.
- Matching uses `fnmatch` with no flags, so `*` crosses spaces and colons, and `?` and `[...]` also work. `bash.execute:python*` matches a bash command starting with `python`.
- **Bash specialisation.** `BashServer::get_permission_pattern` (`src/mcp/servers/bash.cpp:200`) generates the "Always Allow" pattern as `bash.execute:<base command> *`, where the base command is the text before the first space. Matching then compares that against the full command line, so `bash.execute:git *` matches `git status` but not a bare `git` with no arguments. I read that as an edge case, not a bug I confirmed.
- **Deny wins over allow**, but only in step 4. A call on the allow list with a matching deny entry still reaches `execute`, is denied there, and returns an error.

**Things that look off in the source**

- The `PermissionManager` header says "tools must be explicitly allowed or approved via callback". In `check_approval`, though, the callback path sets `approved = true` unconditionally after calling `on_tool_call`. As the body reads, the callback is a notification and not a yes/no gate, so a call with no allow match and a callback set still gets through step 3. The deny check in step 4 is then the only real stop. This should be confirmed at runtime before relying on it.
- Because `auto_approve` skips step 3 but not step 4, a deny entry still blocks a call even under `auto_approve`.