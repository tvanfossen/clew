**Short answer:** the allow list decides whether a call skips the approval prompt. The deny list is a hard stop that runs later, at execution, and is not bypassed by approval. Both lists use the same matcher.

## Flow

```
tool call
 └─ ToolExecutor::check_dup_or_approval
     ├─ check_duplicate → (duplicate handling, may reject)
     └─ check_approval
         approved = auto_approve_tools
                 || ServerManager::is_explicitly_allowed(name, args)   ← allow list
         if !approved and on_tool_call callback set → approved = true  (see caveat)
         fire ON_PERMISSION_CHECK (informational, "allowed"/"denied")
         !approved → create_denied_message("Permission denied")
 └─ ToolExecutor::execute_tool → ServerManager::execute(name, args)
     ├─ pattern = name + ":" + args_to_pattern(args)
     ├─ PermissionManager::is_denied(name, pattern)  → error JSON "Permission denied"
     └─ route_tool_call → server runs the tool
```

- **Allow** (`is_explicitly_allowed` → `PermissionManager::is_allowed`): returns true if any allow entry matches. Its only effect is to skip the prompt.
- **Deny** (`is_denied`, in `ServerManager::execute`): checked on every call that reaches execution, after approval. It is the one place deny is enforced, so an auto-approved call that matches a deny entry is still blocked. `is_allowed` never consults the deny list. That is why "Deny takes precedence" holds.
- Nothing is loaded from config in the paths I traced. `parse_permissions_config` (`src/config/loader.cpp:365`) builds the initial lists that `ServerManager` passes to `PermissionManager`. I did not trace that wiring in detail.

## What a pattern means

Matching is `fnmatch` (shell globs, `*` also matches `/`), in `PermissionManager::pattern_matches`:

- **`tool`** (no colon): matches every call to that tool. Example: `filesystem.read_file`.
- **`tool:argpattern`** (has a colon): the part before the first colon is glob-matched against the tool name. The whole pattern is then glob-matched against `tool:argvalue`.

Where the argument value comes from:

- `ServerManager::args_to_pattern` uses the **first string-valued argument** in the JSON object, or `*` if the args are empty or unparseable. Only that one argument is ever checked.
- `BashServer::get_permission_pattern` (used when generating "Always Allow" entries) writes `bash.execute:<base_cmd> *`, where the base command is the text before the first space. So `bash.execute:ls *` matches `ls -la` but not `lsof`.
- The default `MCPServerBase::get_permission_pattern` returns the bare tool name, so non-bash tools get tool-level patterns unless they override it.

Persistence: "Always Allow/Deny" calls `PermissionPersister::save_permission`, which adds the pattern under `permissions.allow` or `permissions.deny` in the project YAML. It is idempotent.

## Caveat

In `check_approval`, if `on_tool_call` is set, `approved` becomes `true` unconditionally. The callback's return value is never read. So a registered callback notifies but does not gate; it cannot deny a call. If you rely on the callback to refuse calls, this flow will not do it. Only the deny list and the `auto_approve_tools`/allow logic gate calls. Whether that is intended is a question for the code owner.