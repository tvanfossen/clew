I have enough to answer fully now.

## What actually decides it

The call runs through `ToolExecutor::process_single_call` → `check_call_preconditions` (`src/mcp/tool_executor.cpp:667-694`, `include/entropic/mcp/tool_executor.h`), which chains five gates **in a fixed, short-circuiting order**, per a `gh#14`/v2.1.4 doxygen note:

```
1. check_anti_spiral_hard_block   — engine-level circuit breaker, fires first ("cheaper, short-circuits regardless")
2. check_schema                   — malformed args → rejected_schema
3. check_mcp_authorization        — per-identity MCPAuthorizationManager access level
4. check_tier_allowed             — locked-tier allowlist (gh#83, v2.5.2)
5. check_duplicate / handle_duplicate
6. check_approval_pc → check_approval  — the permission-config gate you're asking about
```

Only if none of 1–5 reject does it reach `check_approval` (`src/mcp/tool_executor.cpp:161-188`), which is where the user's allow/deny configuration actually gets consulted:

```cpp
bool auto_ok = loop_config_.auto_approve_tools
            || server_manager_.is_explicitly_allowed(call.name, args_json);
bool approved = auto_ok;
if (!approved && callbacks_.on_tool_call != nullptr) {
    callbacks_.on_tool_call(...);   // interactive/host approval callback
    approved = true;
}
if (!approved) logger->warn("No approval callback — denying: {}", call.name);
return approved;
```

So the precedence is: **auto-approve flag → explicit allow-list match → host approval callback (always approves if present) → default deny** if no callback is wired at all. `is_explicitly_allowed` builds a pattern from the tool name plus first string arg (`args_to_pattern`) and checks it against `PermissionManager` (`entropic::ServerManager::is_explicitly_allowed` → `PermissionManager::is_allowed`, `include/entropic/mcp/permission_manager.h:59-70`).

Notably, `PermissionManager::is_denied` (`permission_manager.h:38-49`) exists and its doxygen says "deny list takes precedence over allow list," but per the dossier's call graph its only *live* caller is a test — `check_approval` itself never calls `is_denied`. The production approval path only ever calls `is_allowed`; nothing in `ToolExecutor` consults the deny list at dispatch time. That's worth flagging as a possible gap or at least something the index can't reconcile with the header's stated model — I can't tell from the index alone whether deny-list enforcement happens somewhere else (e.g., at persistence/UI time via `PermissionPersister`) or is simply unwired at runtime; that would need reading `src/mcp/tool_executor.cpp` end-to-end or `PermissionManager`'s other callers to confirm.

## What a pattern in each list does

Per `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101-125`, static, fnmatch-based):

- A pattern is split at `:` into a **tool-name glob** and an optional **arg glob**.
- `fnmatch(pattern_tool, tool_name, 0)` must match the tool portion — glob syntax (`*`, `?`, `[...]`), no regex.
- If there's no `:`, tool-name match alone is sufficient — the pattern allows/denies the whole tool regardless of arguments.
- If there is a `:`, the *entire* pattern (`tool:argpattern`) must also `fnmatch`-match against `full_pattern` (`tool_name + ":" + args_to_pattern(args_json)`), where `args_to_pattern` is just the first string value found in the parsed JSON args object, or `"*"` if args are empty/unparseable/non-string.

So concretely: an entry in **allow_list_** matching a call's `tool:arg` pattern via `is_allowed` causes `check_approval` to auto-approve without invoking the host callback (`server_manager_.is_explicitly_allowed`). An entry in **deny_list_**, per the header's documented "default-deny, deny-takes-precedence" model, would cause `is_denied` to short-circuit-refuse — but the index shows no live call site wiring that check into the dispatch path, so as configured today a deny-list pattern's actual runtime effect (versus just being data used by `PermissionPersister`/UI) is something the index can't confirm and would need direct source reading to settle.
