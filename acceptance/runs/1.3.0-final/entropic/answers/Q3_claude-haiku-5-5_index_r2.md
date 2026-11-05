**Short answer:** a call runs only if it clears a fixed sequence of checks in `ToolExecutor`. The allow list does not bypass the deny list, and deny patterns are enforced at execution, so they hold even under `auto_approve`. Two things surprised me, covered below.

## Order of decision

```
tool call
 └─ ToolExecutor::process_single_call          tool_executor.cpp:729
     1. PRE_TOOL_CALL hook                     may cancel
     2. check_call_preconditions               :667
          anti-spiral block → schema → MCP authorization
          → tier allowed_tools/bash_commands → duplicate
          → check_approval_pc                  :705
               └─ check_approval               :161   ← approval gate
     3. execute_tool                           :379
          └─ ServerManager::execute            server_manager.cpp:153
               a. is_denied(tool, "tool:arg")  ← deny gate, always runs
               b. route_tool_call → server
```

**Approval gate (`check_approval`, tool_executor.cpp:161-188).** Approved if either:
- `loop_config_.auto_approve_tools` is set. This comes from `permissions.auto_approve` (`build_loop_config`, entropic.cpp:1489), or
- `ServerManager::is_explicitly_allowed` matches the allow list (server_manager.cpp:286).

If neither holds and an `on_tool_call` callback is registered, the call is approved anyway. See the surprise below. With no callback and no match, the call is denied with "Permission denied".

**Deny gate (`ServerManager::execute`, server_manager.cpp:153-168).** This runs after approval and checks the deny list unconditionally. A match returns `Error: Permission denied` and the tool never runs. Because the deny check ignores `auto_approve`, deny wins over both the allow list and auto-approve.

## What a pattern means

Each call is matched as `tool_name` plus `:` plus an args string. The args string comes from `args_to_pattern` (server_manager.cpp:426): it is the value of the first JSON key if that value is a string, otherwise `*`. Matching is `fnmatch` (no `FNM_PATHNAME`), so `*` also crosses `/` and spaces.

`pattern_matches` (src/mcp/permission_manager.cpp:101) works like this:
- **No colon** (`filesystem.*`, `git.commit`): only the tool name is matched. Every call to that tool matches, whatever its args.
- **With a colon** (`bash.execute:python*`): the tool part must match the tool name, and the whole `tool:arg` string must match the pattern.

Both the allow and deny lists use this same matcher. A deny pattern with no colon blocks the tool entirely. Allow patterns are checked in `is_allowed` and deny patterns in `is_denied`, which log "ALLOWED" or "DENIED" with the matched pattern.

Patterns come from config (`permissions.allow`, `permissions.deny`, `auto_approve`, parsed at loader.cpp:365). "Always Allow/Deny" choices are persisted to the project YAML by `PermissionPersister`, and `add_permission` adds them at runtime. For bash, the generated pattern is `execute:{base_cmd} *` (`bash.h`).

## Surprises

1. **A registered `on_tool_call` callback approves every call.** In `check_approval`, if `approved` is false and `on_tool_call != nullptr`, the code fires the callback and then sets `approved = true` (tool_executor.cpp:170-176). The header calls this "approved via callback", but the code never denies. So a host that installs the callback as a permission prompt gets no gate. Only the deny list still applies. This may be intended as notify-only, but the header text suggests otherwise, so I'd check it before relying on the callback for gating.

2. **Deny patterns with args only see the first key.** `args_to_pattern` takes the first JSON member. The repo does not use `ordered_json`, so nlohmann's default `std::map` ordering applies, which makes "first" the alphabetically first key, not the first argument the model wrote. I derived this from the library default and did not run it. A pattern like `bash.execute:rm *` can miss a dangerous command if the command sits in a key that sorts after another string argument.

Neither point affects the allow-list path or the tier and anti-spiral checks, which run earlier.