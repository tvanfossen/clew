The call's fate is decided in two places. Approval runs first, in `ToolExecutor`. Deny is enforced later, in `ServerManager::execute`. Only the allow-list and a callback are approval-side. The deny list is checked only at execution, so it still applies after anything has been approved.

**Flow for one tool call** (`check_call_preconditions`, `src/mcp/tool_executor.cpp:667`):

```
call
 ├─ anti-spiral hard block        (fires first)
 ├─ schema check
 ├─ MCP key authorization         (check_mcp_authorization)
 ├─ tier allowed_tools            (check_tier_allowed, gh#83)
 ├─ duplicate-call check
 └─ check_approval_pc
      └─ check_approval
           ├─ auto_approve_tools?          → approved
           ├─ is_explicitly_allowed(allow) → approved
           ├─ else on_tool_call callback   → approved = true (see below)
           └─ else                          → denied ("Permission denied")
 ↓ approved
ServerManager::execute
 └─ is_denied(deny list)? → "Error: Permission denied for <tool>"
 └─ route_tool_call
```

**What each list does**

- **allow** (`PermissionManager::is_allowed`): a match skips the prompt. It does not grant execution past a deny match, because deny is checked again in `execute`.
- **deny** (`PermissionManager::is_denied`): a match blocks the call at execute time, even if approval passed. The header says "deny takes precedence," and the code matches that: deny is the last gate.
- Both lists use the same matcher, `pattern_matches`. It splits the pattern on the first `:`:
  - Left side (or the whole pattern if there's no colon) is `fnmatch`ed against the fully-qualified tool name, e.g. `filesystem.*` covers every filesystem tool.
  - No colon means the tool matches with any arguments.
  - With a colon, the full string `tool:<arg>` is `fnmatch`ed against the pattern, e.g. `bash.execute:python*`.
- The argument side comes from `args_to_pattern`, which takes only the **first** JSON member of the arguments. If it is a string, that value is used; otherwise the argument is treated as `*`. Patterns therefore match the first argument, not all of them.
- `fnmatch` is called with flags 0, so `*` also matches `/` and spaces, and matching is case-sensitive.
- Bash's `BashServer::get_permission_pattern` generates `bash.execute:<base_cmd> *`, e.g. `bash.execute:pytest *`. The base-command form is what gets offered for "Always Allow/Deny," and it is saved through `PermissionPersister::save_permission` into `config.local.yaml`. Note that the allow/deny matching path itself uses `args_to_pattern`, not this method. I did not confirm how `ServerManager::get_permission_pattern` joins the two.

**Config sources:** `PermissionsConfig` (`include/entropic/types/config.h:589`) has `allow`, `deny` and `auto_approve`. `parse_permissions_config` reads them from the `permissions:` YAML section.

**Things to check**

- In `check_approval`, if `on_tool_call` is set, `approved` is set to `true` unconditionally after the callback runs. So a registered callback approves every call that reaches it, and the "default-deny" behaviour in the header only holds when no callback is wired. The header says "approved via callback," which reads as if the callback decides. I'd treat this as a possible bug, but I only read the index, not the callback's contract.
- Anything denied by `deny` still reaches `execute` only after approval. A call approved by the callback is blocked there, so deny remains effective either way.