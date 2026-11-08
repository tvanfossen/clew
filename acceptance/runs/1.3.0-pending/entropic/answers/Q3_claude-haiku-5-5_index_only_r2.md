## Short answer

Two layers decide whether a call runs. Approval, in `ToolExecutor`, decides whether the call is *allowed to be attempted*. The deny list, in `ServerManager::execute`, decides whether it *actually runs*. Deny is checked after approval, so a denied tool can still reach the approval prompt.

## The path a call takes

```
model emits tool call
 └─ process_single_call                       (tool_executor.cpp:729)
     1. PRE_TOOL_CALL hook          → can cancel ("Cancelled by hook")
     2. check_call_preconditions   (:667)
        a. anti-spiral hard block
        b. schema check
        c. MCP key authorization    (access levels, not permissions)
        d. tier allowlist
        e. duplicate-call detection
        f. check_approval_pc → check_approval   ◄── permission lists live here
     3. execute_tool               (:379)
        └─ ServerManager::execute  (server_manager.cpp:153)
             is_denied? → "Error: Permission denied" (never routed)
             else route_tool_call → the MCP server
```

**`check_approval`** (tool_executor.cpp:161), the approval step:

1. `approved = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(name, args)`.
2. If not approved and an `on_tool_call` callback is wired, the callback is invoked and `approved = true` unconditionally. The callback returns `void`, so the host cannot refuse through it.
3. If not approved and no callback is wired, the call is denied ("No approval callback — denying").
4. It fires `ON_PERMISSION_CHECK` as informational.

## How a pattern is matched

Patterns come from `permissions.allow` and `permissions.deny` (`parse_permissions_config`, loader.cpp:365). Both lists go into `PermissionManager` (permission_manager.h).

`is_allowed` and `is_denied` scan their list and succeed on the first match. Order within a list does not matter.

`pattern_matches` (permission_manager.cpp:101):

- Split the pattern at its first `:` into a tool part and an optional argument part.
- The tool part is `fnmatch`ed against the fully-qualified tool name, e.g. `filesystem.read_file`.
- With no `:`, the tool match is enough.
- With a `:`, the full `tool:arg` string is also `fnmatch`ed. The arg string is built by `args_to_pattern`, which uses the first argument's string value, or `*` if there are no args or parsing fails.
- `fnmatch` runs with flags 0, so `*` also matches `/` and spaces.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `git.commit` | that tool, any args (no `:`) |
| `bash.execute:python*` | bash calls whose first arg starts with `python` |
| `bash.execute:pytest *` | the form the bash server's "Always Allow" generates (`BashServer::get_permission_pattern`, bash.cpp:200), using the base command |

## What each list does

- **`allow`** — `check_approval` treats a match as approved, so the callback is skipped and the call is not prompted. It does not bypass the MCP key checks, tier allowlist, or duplicate detection, which run earlier.
- **`deny`** — `ServerManager::execute` returns an error without routing. It is checked after approval, so a denied tool that is not allow-listed still goes to the approval callback first. The header's "deny takes precedence" holds in effect because execute checks deny regardless of allow.
- **`auto_approve`** — `auto_approve_tools` skips the approval step entirely. Deny still blocks at execute.
- **Persistence** — "Always Allow/Deny" choices go through `PermissionPersister::save_permission` into `config.local.yaml` (the header says config.local.yaml), under a mutex.
- **Runtime** — `add_permission` (the `PermissionManager` API) adds patterns at runtime.

## Things to check

1. **The callback cannot refuse.** Once `on_tool_call` is set, `check_approval` returns true for every non-allowed call. Only the deny list can block a call in that setup. If the intent was that the host can say no, this is a defect, since `void` makes refusal impossible. I read this from the code; I did not confirm it against the consumer UI.
2. **Prompt-then-deny.** A call matching `deny` but not `allow` gets a prompt, and a "yes" still ends in "Permission denied" at execute. Denied tools should probably be stopped before the prompt. This is also from the code only.
3. The `:` split is on the first colon, so a tool name containing a colon would split wrongly.