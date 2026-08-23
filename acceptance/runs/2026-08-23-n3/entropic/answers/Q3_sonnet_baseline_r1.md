## What decides whether the call runs

Trace the arrival, in order:

**1. `ToolExecutor::process_single_call`** (`src/mcp/tool_executor.cpp:729`) is the entry point. It first fires a `PRE_TOOL_CALL` hook (can cancel outright), then runs `check_call_preconditions()` (`tool_executor.cpp:667`) as a strict pipeline where any earlier failure short-circuits the rest:

1. anti-spiral hard block (repeated-call loop guard — not user config)
2. JSON-schema arg validation
3. `check_mcp_authorization` — a *separate* per-identity/MCP-key access-level check, unrelated to the allow/deny lists
4. `check_tier_allowed` — enforces the locked tier's `allowed_tools` list
5. duplicate-call suppression
6. **`check_approval`** (`tool_executor.cpp:161`) — this is where the user-configured permission lists actually get consulted

`check_approval` logic:
```cpp
bool auto_ok = loop_config_.auto_approve_tools
            || server_manager_.is_explicitly_allowed(call.name, args_json);
bool approved = auto_ok;
if (!approved && callbacks_.on_tool_call != nullptr) {
    callbacks_.on_tool_call(call_json, user_data);  // notify host
    approved = true;                                 // unconditional approve once fired
}
```
Note `on_tool_call` is a *notification* callback, not a yes/no gate — if it's wired up, firing it always approves; the deny list is enforced elsewhere, not here.

**2. `ServerManager::execute()`** (`src/mcp/server_manager.cpp:153`) re-checks the deny list independently before dispatch — defense in depth.

## Config schema

`PermissionsConfig` (`include/entropic/types/config.h:589`):
```cpp
struct PermissionsConfig {
    std::vector<std::string> allow;   // glob patterns
    std::vector<std::string> deny;    // glob patterns
    bool auto_approve = false;
};
```
Loaded from a `permissions:` YAML block (`src/config/loader.cpp:357`) with `allow:`/`deny:` lists and an `auto_approve:` bool. `auto_approve` becomes `loop_config_.auto_approve_tools`, which — if true — bypasses the allow list and the prompt callback entirely.

## What a pattern in each list does

Matching is glob (`fnmatch()`, POSIX semantics: `*`, `?`, `[...]`) — **not regex** — implemented in `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`):

- **No colon** (e.g. `filesystem.*`, `bash.*`): glob-matched against the tool name only. `bash.*` = "allow/deny all bash tool calls," matching any tool name. (Note: `shell:*`-with-colon syntax is *not* "match all" — see next point.)
- **With a colon** (e.g. `bash.execute:python*`): the part before `:` must glob-match the tool name, *and* the whole pattern is then glob-matched against `tool_name + ":" + args_to_pattern(args)`, where `args_to_pattern` reduces the JSON args to essentially "first argument value." So `bash.execute:python*` matches bash.execute calls whose first arg starts with "python".
- A pattern with no wildcard characters at all (e.g. `git.commit`) degenerates to an exact tool-name match.

Both the allow list (`is_explicitly_allowed`) and the deny list (`is_denied`) use this same matcher and scan linearly, returning on the first match — first-match-wins within a list, but since the result is boolean, multiple matches are equivalent (effectively any-match-wins per list).

## Precedence rules

- **Default-deny model, deny overrides allow.** `ServerManager::execute()` checks `is_denied` first and short-circuits with an error before any allow/dispatch logic runs (`server_manager.cpp:159`). The allow list only ever decides whether to *skip prompting*; it never overrides a deny.
- **No most-specific-wins** — it's a flat scan per list.
- **Unmatched tools are not denied by `PermissionManager` itself** ("the engine handles prompting for tools not in either list" per the header comment) — the actual fallback is one layer up in `check_approval`: `auto_approve` flag → else fire `on_tool_call` (always approves once fired) → else deny by default.

Key files: `include/entropic/mcp/permission_manager.h`, `src/mcp/permission_manager.cpp`, `include/entropic/types/config.h:585-593`, `src/config/loader.cpp:357-374`, `src/mcp/tool_executor.cpp:161-763`, `src/mcp/server_manager.cpp:153-165,286-311`.
