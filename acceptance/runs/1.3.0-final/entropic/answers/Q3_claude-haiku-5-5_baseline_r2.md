Short answer: the allow list only decides whether the approval prompt is skipped. The deny list is checked later, at execution, and is the only list that can stop a call that was already approved. There is no separate "ask" list. A call that matches neither list goes to the host callback, and if no callback is registered it is denied.

## Decision path

```
model emits tool call
└─ ToolExecutor::check_call_preconditions          tool_executor.cpp:667
   1. anti-spiral hard block
   2. schema validation (check_schema)
   3. MCP key set for identity (check_mcp_authorization, :575)
   4. tier allowed_tools (check_tier_allowed, :198)
   5. duplicate detection
   6. approval (check_approval_pc → check_approval, :161)
        auto_ok = auto_approve OR allow-list match
        if !auto_ok and on_tool_call set  → approved = true
        if !auto_ok and no callback        → denied "Permission denied"
└─ process_single_call → ServerManager::execute     server_manager.cpp:153
   7. deny-list match → "Error: Permission denied for <tool>"
   8. route to in-process server or external client
```

Steps 1–5 run before either list is consulted, so neither list bypasses MCP keys, tier `allowed_tools`, schema checks, or duplicate detection. The lists are loaded from `permissions.allow`, `permissions.deny` and `permissions.auto_approve` (`config/loader.cpp:365`), and handed to `PermissionManager` through the `ServerManager` constructor (`server_manager.cpp:35`).

## What a pattern does

- **Allow pattern:** if it matches, step 6 is skipped and the call proceeds to execution. Nothing else changes. The deny list still applies at step 7.
- **Deny pattern:** if it matches, the call returns an error result at step 7, even if auto-approve or an allow match approved it. Deny always wins.
- **Matching** (`permission_manager.cpp:101`): the pattern is split at the first `:`. The left side is fnmatched against the tool name. With no `:`, that is the whole test (tool-level). With a `:`, the full pattern is fnmatched against `tool_name:<arg-pattern>`.
- **Arg pattern** (`server_manager.cpp:426`): the value of the first string-valued argument, where "first" means alphabetically first key because nlohmann objects are sorted maps. If the first arg isn't a string or there are no args, it becomes `*`.

Examples:

| Pattern | Effect |
|---|---|
| `filesystem.*` | every filesystem tool, any args |
| `bash.execute` | every bash call, any command (no colon) |
| `bash.execute:git *` | bash commands starting with `git ` |
| `filesystem.write_file:/etc/*` | writes under `/etc` |

## Things to watch

1. **The host callback cannot deny.** `on_tool_call` is `void(const char*, void*)` (`engine_types.h:370`), and `check_approval` sets `approved = true` after calling it. The `tool_executor.h` header says tools are "approved via callback", which doesn't match the code. With a callback registered, the only way a call is refused is the deny list. Confirm this against your intended design before relying on the callback as a gate.
2. **Glob matching has no path or word boundaries.** `fnmatch` runs without `FNM_PATHNAME`, so `*` matches `/`, spaces and shell operators. An allow of `bash.execute:ls*` also allows `ls; rm -rf ~`, because only the command text is matched. Deny patterns are equally porous, so for bash, deny-by-prefix is weak.
3. **Only the first string argument is matched.** Any other argument is invisible to both lists.
4. **Bash's `get_permission_pattern` is dead code on the decision path.** `BashServer::get_permission_pattern` (`bash.cpp:200`) builds `bash.execute:<base> *`, but both `is_denied` and `is_explicitly_allowed` call `args_to_pattern` directly, and `ServerManager::get_permission_pattern` has no callers. Patterns match the raw command text as above.
5. **`auto_approve: true` skips the prompt for everything not denied,** including tools with no allow entry.
6. **Runtime "always allow" persistence isn't wired in `src/`.** `set_permission_persist` stores the callbacks, but I found no caller of `add_permission` or of the persister in `src/`, so patterns can only come from config.

I didn't run the test suite. These findings come from reading the code.