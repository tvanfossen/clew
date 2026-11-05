**Short answer:** a call runs only if it clears the precondition chain in `ToolExecutor`, the approval gate, and then the deny check at dispatch. The allow and deny lists are matched with `fnmatch`. The deny list is the only hard stop, and it is checked after approval.

## The path a call takes

```
model emits tool call
 └─ ToolExecutor::process_single_call            tool_executor.cpp:729
     ├─ PRE_TOOL_CALL hook can cancel            :733
     └─ check_call_preconditions                 :667  (first rejection wins)
         ├─ anti-spiral hard block
         ├─ schema validation (required/enum/type)
         ├─ MCP key check (per-identity)         :575  only if identity registered
         ├─ tier allowed_tools                   :198
         ├─ duplicate-call check
         └─ check_approval                       :161
             ├─ auto_approve_tools?  ──────────────► approved
             ├─ allow list match?    ──────────────► approved
             ├─ on_tool_call callback set? ──► approved = true (callback return is ignored)
             └─ else                 ──────────────► DENIED "No approval callback"
     └─ execute_tool → ServerManager::execute    server_manager.cpp:153
         └─ deny list match? ──► "Error: Permission denied"   (deny wins, even with auto_approve)
         └─ else route to in-process or external server
```

Points that matter:

- **The approval callback does not gate anything.** `on_tool_call` is `void(*)(const char*, void*)` (`engine_types.h:370`). Once it is set, `check_approval` marks the call approved without reading any result (`tool_executor.cpp:168-172`). The header's "approved via callback" wording is therefore misleading. With a callback wired, the only thing that stops a call is the deny list.
- **Deny is checked after the prompt.** A call that matches `deny` still triggers `on_tool_call`, so the user may see a prompt for a call that is then refused.
- **`auto_approve` does not bypass deny.** It only skips the approval step; `ServerManager::execute` always checks the deny list.
- **Without a callback, the default is deny.** A call is denied unless `auto_approve` is set or the allow list matches. That is the only real default-deny behaviour.
- **The header's "default-deny" claim holds only in headless mode.** With a callback wired, the default is effectively allow-with-notification.

## What a pattern does

Config keys are `permissions.allow`, `permissions.deny` and `permissions.auto_approve` (`loader.cpp:369-371`). The matcher is `PermissionManager::pattern_matches` (`permission_manager.cpp:101`):

1. Split the pattern at the first `:`.
2. Left side: `fnmatch` against the tool name, e.g. `filesystem.*`.
3. Right side, if present: `fnmatch` against `tool:<argvalue>`.

Argument value: `args_to_pattern` (`server_manager.cpp:426`) takes the first JSON key's value, if it is a string. Iteration order is nlohmann's default, which is sorted by key, so "first" means alphabetically first, not first in the schema. If there is no string arg, or parsing fails, the value is `*`.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `git.commit` | that tool only, any args (no colon) |
| `filesystem.read_file:/home/*` | that tool when its first string arg starts with `/home/` |
| `bash.execute:git *` | `bash.execute` whose command starts with `git ` |

Behaviour to be aware of:

- **`fnmatch` flags are 0**, so `*` also matches `/`. `/home/*` covers deep paths. There is no path normalisation, so `..` segments are not caught.
- **Bash prefix rules can be bypassed.** `bash.execute:git *` matches the whole command string, so `git status; rm -rf ~` matches the allow rule. The bash server's own comment says approval is the gate, so this is a real gap if `allow` is used for bash.
- **`BashServer::get_permission_pattern` (`bash.cpp:200`) is dead code.** Nothing calls `ServerManager::get_permission_pattern`. Both `is_denied` and `is_allowed` use `args_to_pattern`. The "execute:{base_cmd} *" design in that override is not what is enforced.
- **Allow and deny are both first-match boolean checks.** Order in the list does not matter, and deny overrides allow.
- **Runtime additions**: `add_permission` (`server_manager.cpp:359`) appends and de-duplicates. `PermissionPersister::save_permission` writes YAML, but nothing in `src/` calls it, and `PermissionPersistFn` is declared but never invoked. "Always allow" does not persist in this tree.

## Related: MCP keys

`MCPAuthorizationManager` is a separate check that runs before approval. It is enforced only for identities that have been registered (`mcp_authorization.cpp:37`). An unregistered identity is allowed by default (`check_access`, line 100). It is not part of the `allow`/`deny` lists.

## Discrepancy

`data/schemas/config_schema.json:61-62` names the keys `allow_patterns` and `deny_patterns`, but the loader reads `allow` and `deny`. Either the schema or the loader is wrong. I did not check which one users' configs follow.

I read the code but did not run anything, so the bypass and ordering claims are from reading, not from a test.