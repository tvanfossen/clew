**Short answer:** the tier and MCP-key checks run first and can reject a call outright. After that, the allow list decides whether the call runs without prompting, and the deny list is enforced later, at execution, not in the approval step. One part of the approval code does not match how the config reads, and I flag it below.

## What decides a call (in order)

The chain is `ToolExecutor::check_call_preconditions` (`src/mcp/tool_executor.cpp:667`). The first rejection wins:

1. **Anti-spiral hard block:** rejects a tool that has been called too many times in a row.
2. **Schema check:** the arguments must validate against the tool's schema.
3. **MCP key authorization:** `check_mcp_authorization` against the locked identity.
4. **Tier `allowed_tools`:** `check_tier_allowed` (gh#83). If the locked tier has a non-empty allowlist and the tool isn't in it, the call is denied even if it is allow-listed.
5. **Duplicate detection:** an identical repeated call is bounced with feedback.
6. **Approval:** `check_approval_pc` → `ToolExecutor::check_approval` (`tool_executor.cpp:161`).

`check_approval` works like this:

- Approved if `loop_config_.auto_approve_tools` is set, or if `ServerManager::is_explicitly_allowed` returns true.
- `is_explicitly_allowed` builds `tool_name + ":" + args_to_pattern(args)` and checks **only the allow list** (`PermissionManager::is_allowed`).
- If not approved and an `on_tool_call` callback is registered, the callback fires and then `approved = true` unconditionally (line 170-171 of the body I read). **The callback's result is ignored.**
- If no callback is registered, the call is denied with "Permission denied".

The deny list is not consulted in `check_approval`. `PermissionManager::is_denied` has one indexed caller, named `execute`, and `ServerManager::execute`'s doc says it "checks permissions before execution" and returns an error if denied. So a deny match stops the call at dispatch, after approval has already passed. I could not resolve `ServerManager::execute` by its qualified name, so the exact call site is inferred from that caller edge and the doc comment.

## What a pattern does

Patterns are `tool` or `tool:arg`, matched with `fnmatch` by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`):

| Pattern | Matches |
|---|---|
| `filesystem.read_file` | That tool, any arguments. No colon means the tool name alone decides. |
| `filesystem.*` | Every filesystem tool (glob on the tool half). |
| `bash.execute:pytest *` | `bash.execute` only, when its first argument matches the glob `pytest *`. |
| `*` | Every tool. |

The argument half comes from `args_to_pattern` (`server_manager.cpp:426`). It takes the value of the first JSON key if that value is a string, and falls back to `*` for empty or non-string args. So "first argument" means the first key in the JSON object, not a named parameter.

Each list is an OR over its patterns. The deny list is checked on execution, so a deny match blocks a call even when an allow pattern matches it. The header comment's "deny takes precedence" holds because of that execution-time check, not because of the approval step.

## Where patterns come from

- **Config:** `permissions.allow`, `permissions.deny`, `permissions.auto_approve` (`PermissionsConfig`, `config.h:589`). The global file is `~/.entropic/config.yaml`; the project file is `.entropic/config.local.yaml`.
- **"Always Allow/Deny" at runtime:** `get_permission_pattern` generates the pattern. The default is tool-level (the bare tool name), and `BashServer` overrides it for finer granularity. The pattern is then saved by `PermissionPersister::save_permission` into `permissions.allow` or `permissions.deny` in `config.local.yaml`, under the same write mutex.

## Things to check

- **The callback approves everything.** If a host registers `on_tool_call`, every call that misses the allow list still runs, because the callback's return is discarded. If the host expects the callback to be a gate, this is a bug. I'd verify it with a test before relying on it.
- **Deny is not in the approval step.** Anything that bypasses `ServerManager::execute` would skip the deny list entirely. The index can't confirm that path, so read `ServerManager::execute` directly.