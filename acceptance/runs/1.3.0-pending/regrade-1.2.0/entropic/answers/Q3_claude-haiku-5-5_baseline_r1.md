**Short answer:** the call runs only if it clears every precondition in `ToolExecutor`, then `ServerManager::execute` does a final deny check before routing. The allow list is a skip-prompt shortcut, and the deny list is enforced later than you might expect.

## Order of checks

```
tool call
 │
 ├─ PRE_TOOL_CALL hook            (can cancel: "Cancelled by hook")
 ├─ check_anti_spiral_hard_block
 ├─ check_schema                  (argument validation against tool schema)
 ├─ check_mcp_authorization       (identity MCP keys, if enforced)
 ├─ check_tier_allowed            (locked tier's allowed_tools, gh#83)
 ├─ check_duplicate
 ├─ check_approval                (tool_executor.cpp:161)
 │    ├─ auto_approve_tools?  ──────────────── yes → approved
 │    ├─ is_explicitly_allowed (allow list)? ─ yes → approved
 │    └─ on_tool_call callback set? ────────── yes → approved (return value ignored)
 │
 └─ ServerManager::execute        (server_manager.cpp:153)
      ├─ is_denied (deny list)?  ── yes → "Error: Permission denied for <tool>"
      └─ route_tool_call → in-process server or external MCP client
```

The relevant code:
- `src/mcp/tool_executor.cpp:667` — `check_call_preconditions`, the chain above.
- `src/mcp/tool_executor.cpp:161` — `check_approval`.
- `src/mcp/server_manager.cpp:153` — `execute`, where the deny check happens.
- `src/mcp/permission_manager.cpp` — the matching logic.
- `src/mcp/mcp_authorization.cpp` — per-identity MCP keys, a separate layer from the allow/deny lists.

## What a pattern does

Each entry is `tool_pattern` or `tool_pattern:arg_pattern`, matched with `fnmatch` (`permission_manager.cpp:101`):

1. The part before the first `:` is matched against the fully-qualified tool name, e.g. `bash.execute`.
2. With no `:`, a tool match is enough. `filesystem.*` covers every filesystem tool regardless of arguments.
3. With a `:`, the full string `tool:arg` is also matched against `tool_name + ":" + first_string_arg`.

Arguments are reduced by `args_to_pattern` (`server_manager.cpp:426`) to the value of the first string-valued argument, or `*` if there is none. So for bash, the value is the whole command string.

The two lists behave differently:
- **Allow** entries are checked in `check_approval` and only let a call skip the prompt. They do not bypass the later deny check.
- **Deny** entries are checked in `ServerManager::execute`, after approval has already passed. A tool that matches both lists is approved and then denied at dispatch.

## Things I found that you may want to check

- **The approval callback doesn't gate anything.** In `check_approval`, if `on_tool_call` is set, `approved` becomes `true` and the callback's result is discarded (the callback type returns `void`). So a host with a callback never blocks a call through that path. Only the deny list, the MCP keys, the tier allowlist, or `auto_approve` being off with no callback would stop it. I read this from the code and did not run it.
- **Bash allow patterns use wildcards that cross command separators.** `fnmatch` without `FNM_PATHNAME` lets `*` match anything, so `bash.execute:python*` also matches `python x; rm -rf /`. That is a consequence of the matcher, not something I tested.
- **`BashServer::get_permission_pattern` appears unused.** It builds `bash.execute:<base_cmd> *`, but a grep finds no caller. Matching uses `args_to_pattern` on the raw command instead, so the base-command form in that method doesn't apply.
- **Denied calls look like tool errors to the model.** The deny path returns `Error: Permission denied for <tool>`, not the `create_denied_message` format used by the earlier gates.

I didn't run the test suite. The findings come from reading `src/mcp/` and the call sites.