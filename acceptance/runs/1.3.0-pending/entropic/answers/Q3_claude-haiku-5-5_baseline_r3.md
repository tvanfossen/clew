The short answer: a call runs only if it clears a fixed chain of gates in `ToolExecutor`, and the allow/deny lists feed into only two of those gates. Deny is enforced a second time, later, inside `ServerManager::execute`. Nothing I read in the approval path lets a user-facing prompt veto a call.

## The decision path

```
ToolExecutor::process_single_call          (src/mcp/tool_executor.cpp:729)
  1. PRE_TOOL_CALL hook                    → may cancel ("Cancelled by hook")
  2. check_call_preconditions              (:667)
     a. anti-spiral hard block
     b. check_schema                       → argument validation
     c. check_mcp_authorization            → MCP key set for the locked tier (:575)
     d. check_tier_allowed                → tier's allowed_tools (gh#83)
     e. check_duplicate                   → repeated identical call
     f. check_approval_pc → check_approval (:161)
        ├─ auto_ok = permissions.auto_approve
        │            OR ServerManager::is_explicitly_allowed (allow list)
        ├─ if !auto_ok and on_tool_call callback set → callback, approved = true
        └─ else denied ("Permission denied")
  3. execute_tool → ServerManager::execute (server_manager.cpp:153)
        ├─ is_denied(tool, pattern)  → "Error: Permission denied" (deny list)
        └─ route_tool_call → in-process server or external MCP client
```

The gates that actually decide:

- **Allow list** (`permissions.allow`) is the only thing that skips prompting. `auto_approve: true` skips it for everything.
- **Deny list** (`permissions.deny`) is checked only in `ServerManager::execute`, after approval has already happened. `check_approval` never consults it.
- **Callback** (`on_tool_call`) is `void`-returning. Its mere presence sets `approved = true` (`tool_executor.cpp:168-172`). It can notify but cannot refuse.
- **No callback and no allow match** means the call is denied.

## What a pattern in each list does

Lists are loaded from `permissions.allow` / `permissions.deny` (`config/loader.cpp:369`) into `PermissionManager` (`permission_manager.cpp`). Each pattern is split at the first `:`.

| Pattern | Left of `:` | Right of `:` | Matches |
|---|---|---|---|
| `bash.execute` | tool name, fnmatch against `bash.execute` | none | every call to that tool |
| `filesystem.*` | fnmatch on the tool name | none | all filesystem tools |
| `bash.execute:python*` | fnmatch on the tool name | fnmatch on `tool:argvalue` | calls whose first string argument starts with `python` |

The argument value comes from `args_to_pattern` (`server_manager.cpp:426`). It takes the first string value of the JSON args object, or `*` if there are none. For bash that is the whole `command` string, so the match is `bash.execute:<command>`.

Matching uses `fnmatch` with flags 0, so `*` also matches `/` and shell separators. A rule `bash.execute:ls*` therefore allows `ls; rm -rf ~` as well. Rules are a convenience, not a sandbox. The `command` value is what the bash server's own comment says the operator approves.

## Things that don't match the header docs

1. **The header says "default-deny … approved via callback."** In practice the callback can't say no. Any registered callback approves. Without a callback, only allow-list hits and `auto_approve` run.
2. **Deny is not checked at the approval gate.** With `auto_approve: true` a denied tool still gets `auto_ok`. It is stopped only at `ServerManager::execute`, so it does get blocked, but the error comes back as a tool result rather than a permission rejection.
3. **`BashServer::get_permission_pattern` is dead code.** Nothing calls `ServerManager::get_permission_pattern`, so the live pattern is always the raw first-argument value, not `bash.execute:<base-cmd> *`.
4. **Tier and MCP-key checks run before approval.** An allow-list entry does not bypass them. A tier whose `allowed_tools` excludes the tool, or an identity lacking the MCP key, is rejected first.

I did not build or run tests; these are readings of the source. The tests that would confirm them are in `tests/unit/mcp/permission_manager_test.cpp` and `tests/unit/mcp/tool_executor_test.cpp`, and `tool_executor_authorization_test.cpp` covers the auth gate.