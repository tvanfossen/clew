The earlier search result already gave the file-doc brief in full; that's enough. Now I have the complete decision chain.

## The decision chain

A tool call from the model reaches `entropic::ToolExecutor::process_single_call` → `check_call_preconditions` (`include/entropic/mcp/tool_executor.h:667`, impl in `src/mcp/tool_executor.cpp:667-694`), which runs a **fixed, short-circuiting sequence of gates**, each of which can kill the call before it ever executes:

1. **`check_anti_spiral_hard_block`** — fires first, deliberately, per gh#83 (v2.1.4 comment): cheapest check, and short-circuits a tool the engine has already decided to refuse regardless of what the other gates would say.
2. **`check_schema`** — malformed/invalid args → `rejected_schema`.
3. **`check_mcp_authorization`** — only active if an `MCPAuthorizationManager` is wired (`auth_mgr_`). Resolves the caller's identity from `ctx.locked_tier` (default `"lead"`), looks up the tool's `required` access level via `ServerManager::get_required_access_level`, and denies if `auth_mgr_->check_access(identity, tool, required)` fails. This is a capability check, independent of the allow/deny lists below.
4. **`check_tier_allowed`** — enforces a locked tier's `allowed_tools` list (gh#83, v2.5.2) at dispatch time, not just prompt-injection time. Passes through if no tier is locked, no tier map is wired, or the tier's list is empty (unrestricted); otherwise the call name must literally appear in that tier's list.
5. **`check_duplicate`/`handle_duplicate`** — repeat-call suppression.
6. **`check_approval_pc` → `check_approval`** — this is where **user-configured permissions** actually decide the call (`src/mcp/tool_executor.cpp:161-188`):
   - `auto_ok = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(call.name, args_json)`.
   - `is_explicitly_allowed` (`server_manager.cpp:286`) builds a pattern string `"tool_name:arg_pattern"` via `args_to_pattern` and calls `PermissionManager::is_allowed`.
   - If not auto-approved, and an `on_tool_call` callback exists, it's invoked (interactive prompt) and treated as approval.
   - Fires the `ON_PERMISSION_CHECK` hook informationally either way.
   - If still not approved, the call is denied and logged: `"No approval callback — denying"`.

Note: `PermissionManager::is_allowed`/`is_denied` themselves aren't both consulted in this path shown — `is_explicitly_allowed` only calls `is_allow`ed. **Deny-list precedence is documented at the class level** ("Default-deny permission model... Deny list takes precedence over allow list") but the actual precedence enforcement point (where `is_denied` is also checked before/instead of `is_allowed`) sits elsewhere in the flow — likely in `ServerManager`'s caller logic or the interactive-approval path; the index shows `is_denied`'s only callers as `TEST_CASE` and a generic `execute` (ambiguous — 49 candidate overloads, not resolved to one). I did not trace that second call site definitively; that's a gap, not an inference.

## What a pattern in each list does

From `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101-125`), both `allow` and `deny` list entries use the same syntax:

- A pattern is `tool_name` or `tool_name:arg_pattern`.
- `tool_name` is matched against the fully-qualified tool name with **POSIX `fnmatch`** (shell-glob) semantics — `*`, `?`, `[...]` work as globs, not regex.
- If there's no `:`, tool-name match alone is sufficient — the pattern allows/denies the tool regardless of arguments.
- If there is a `:`, the full pattern (`tool_name:arg_pattern`) must additionally `fnmatch` against the full call string (`tool_name:args`) — so the arg portion can glob-constrain which argument values are permitted, e.g. restricting a `bash.execute` allow to a specific command prefix.

So an **allow-list pattern** grants auto-approval (skips prompting) for calls matching it; a **deny-list pattern** is documented to force rejection and take precedence — `is_denied` exists and is exercised in tests, but I could not confirm from the index which live call site outside tests enforces that precedence in the traced `ToolExecutor` path. Flagging that as an honest gap rather than asserting it.
