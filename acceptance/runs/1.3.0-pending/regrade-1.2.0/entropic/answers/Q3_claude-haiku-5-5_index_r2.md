## What decides whether a call runs

Two checks decide it, and they run at different layers. The approval check in `ToolExecutor` comes first, and the deny-list check in `ServerManager::execute` comes second, right before routing.

```
process_single_call                       (src/mcp/tool_executor.cpp:729)
 ├─ PRE_TOOL_CALL hook ──────────────────► "Cancelled by hook"
 ├─ check_call_preconditions
 │    └─ approval layer ─► check_approval  (tool_executor.cpp:161)
 │         ├─ auto_approve_tools ─────────► approved
 │         ├─ is_explicitly_allowed ─────► approved   (allow list)
 │         ├─ on_tool_call callback set ─► approved   (see caveat)
 │         └─ otherwise ─────────────────► "Permission denied"
 └─ execute_tool                           (tool_executor.cpp:379)
      └─ ServerManager::execute            (server_manager.cpp:153)
           ├─ is_denied(tool, pattern) ───► "Error: Permission denied"
           └─ route_tool_call ────────────► the MCP server runs
```

Two things stand out:

- **The deny list runs after approval.** A call on the deny list still goes through `check_approval` first. If a callback is registered, the user can be asked about a call that will then be refused. A deny match also overrides `auto_approve` and the allow list, because it is checked unconditionally in `execute`.
- **The callback does not gate anything.** `check_approval` fires `on_tool_call` and then sets `approved = true` without reading a return value. With a callback registered, every call passes the approval layer. The header comment in `permission_manager.h` describes default-deny with "approved via callback", which doesn't match this code. I didn't check the Python binding, so I can't say whether the host enforces anything there.

## What a pattern means

Patterns live in `permissions.allow` and `permissions.deny` (`PermissionsConfig`, `include/entropic/types/config.h:589`), parsed by `parse_permissions_config` (`src/config/loader.cpp:365`). `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`) splits each pattern at the first `:`:

| Pattern | Left of `:` matches | Right of `:` matches | Effect |
|---|---|---|---|
| `filesystem.read_file` | fnmatch against the tool name | (none) | Every call to that tool, any args |
| `filesystem.*` | fnmatch against the tool name | (none) | Every filesystem tool |
| `bash.execute:ls *` | fnmatch against `bash.execute` | fnmatch against `bash.execute:<first arg>` | Only calls whose first arg matches the glob |

- The right side is matched against the tool name plus the first string value in the args JSON (`ServerManager::args_to_pattern`, `server_manager.cpp:426`). Empty args, `{}`, or a non-string first value all become `*`.
- `is_allowed` and `is_denied` use the same matcher. `is_allowed` logs "Permission ALLOWED" and returns on the first matching entry.
- `add_permission` (`permission_manager.cpp:79`) skips exact duplicates, and `PermissionPersister` writes the new entries back to project YAML.
- The "Always Allow" pattern is generated per server. The default is the bare tool name (`MCPServerBase::get_permission_pattern`, `server_base.cpp:87`). `BashServer` overrides it to `tool:<base_cmd> *` (`bash.cpp:200`), so approving `git status` stores `bash.execute:git *`.

**Concern with the bash pattern:** `fnmatch` without `FNM_PATHNAME` lets `*` match spaces and `;`. Since the match runs against the full first argument, `bash.execute:git *` should also match `git status; rm -rf ~`. I read this from the code but did not run it. If it holds, a base-command allow entry permits chained commands, and a deny entry is the only guard. Add a test that checks it.

## Not traced

- Which of `check_approval_pc` or `check_dup_or_approval` the precondition chain actually calls.
- How the config lists are copied into `ServerManager::permissions_` at construction.