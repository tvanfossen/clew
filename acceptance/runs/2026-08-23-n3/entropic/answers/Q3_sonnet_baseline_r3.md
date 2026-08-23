Now I have the whole chain grounded in the actual source. Here's the trace.

## What actually decides it

A tool call from the model lands in `ToolExecutor::process_single_call` (`src/mcp/tool_executor.cpp`), which runs a fixed gauntlet **before** the call ever reaches a server. Any one of these can reject it, and it's checked in this order (`check_call_preconditions`, with the pre-tool hook running even earlier):

1. **Pre-tool hook** (`PRE_TOOL_CALL`) — a plugin can veto outright, informationally, before anything else.
2. **Anti-spiral hard block** — same tool called too many times consecutively. Cheap, checked first among preconditions.
3. **Schema check** — args validated against the tool's JSON Schema (required fields, enum, type).
4. **MCP authorization** (`MCPAuthorizationManager::check_access`) — per-identity key set. Only enforced if the identity was ever `register_identity()`'d; unregistered identities pass through untouched (backward-compat default).
5. **Tier `allowed_tools`** (gh#83) — if the identity is a locked tier with a declared allowlist, the call name must be literally in it.
6. **Duplicate-call detection** — same name+args seen recently → short-circuited with the cached result or a circuit-breaker message after 3 repeats.
7. **Approval** — `check_approval()`. This is where the user's configured **allow/deny lists** actually enter:
   - `loop_config_.auto_approve_tools` short-circuits everything (approve all), OR
   - `server_manager_.is_explicitly_allowed(name, args_json)` → delegates to `PermissionManager::is_allowed`.
   - If neither, and an `on_tool_call` callback is registered, that callback is invoked and the call is treated as approved unconditionally (there's no actual veto path back from the callback in this code — calling it *is* the approval).
   - If no callback exists, it's denied by default (default-deny).

Only after clearing all of that does `execute_tool` run, which calls `ServerManager::execute()` — and that itself does a **second**, redundant deny check (`permissions_.is_denied(tool_name, pattern)`) right before routing to the actual server. So the deny list is actually consulted twice on two different paths (`check_approval`'s `is_allowed` and `execute`'s `is_denied`), while the allow list is only consulted once, inside `check_approval`.

## The permission lists themselves

`PermissionsConfig` (`include/entropic/types/config.h`) holds `allow` and `deny` as vectors of glob patterns, user-configurable (e.g. via `~/.entropic/config.yaml` / `.entropic/config.local.yaml`), fed into a `PermissionManager` owned by `ServerManager`.

**What one pattern in the list does**, per `PermissionManager::pattern_matches` (fnmatch semantics, from `permission_manager.h`'s doc comment and the implementation):

- The pattern is split at the first `:` into a tool-name glob and an optional argument-pattern glob.
- The tool-name portion is matched against the fully-qualified tool name (`server.tool`) via `fnmatch`. E.g. `"filesystem.*"` matches every filesystem tool.
- If there's no `:`, a tool-name match alone is sufficient — the pattern hits regardless of arguments.
- If there is a `:`, the *full* pattern (`tool_name:arg_pattern`) must also `fnmatch`-match the full call signature (`tool_name:serialized_args`), e.g. `"bash.execute:python*"` only matches `bash.execute` calls whose serialized-args pattern starts with `python`.

And the precedence rule that actually governs the outcome: **deny beats allow.** Concretely, `ServerManager::execute` denies on any deny-list match regardless of what the allow list says (that check runs unconditionally at execution time), and `check_approval`'s `is_allowed` lookup is only ever consulted to *skip prompting* — it never overrides a deny. A tool with no match in either list is not auto-denied by `PermissionManager` itself; it falls through to the approval callback, and absent that callback, `check_approval` denies it by default. So the net model is: default-deny, allow-list bypasses the prompt, deny-list is an unconditional veto checked at two separate points in the call path.
