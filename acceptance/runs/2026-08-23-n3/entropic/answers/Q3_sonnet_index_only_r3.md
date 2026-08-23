## The decision chain

A tool call from the model reaches `ToolExecutor::process_single_call`, which runs `check_call_preconditions` — a fixed, short-circuiting sequence (`tool_executor.cpp:667-694`):

```
1. check_anti_spiral_hard_block   — engine already decided to refuse this tool → reject, cheapest first
2. check_schema                   — malformed args → reject
3. check_mcp_authorization        — per-identity MCP key set lacks required access level → reject
4. check_tier_allowed             — locked tier's allowed_tools list doesn't contain this tool → reject
5. check_duplicate / handle_duplicate
6. check_approval_pc → check_approval  — the permission system proper
```

Only if all five earlier gates pass does the **allow list** ever get consulted, and even then it isn't the final word — a second, independent check happens later at actual dispatch.

## Where the allow/deny lists come in

**`check_approval`** (`tool_executor.cpp:161-188`) decides whether the model needs a human/callback approval at all:
```
auto_ok = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(name, args)
```
`is_explicitly_allowed` builds `pattern = tool_name + ":" + args_to_pattern(args_json)` and checks it against `PermissionManager::allow_list_` via `is_allowed`. If it matches, the call is approved with **no prompt**. If not, it falls to the `on_tool_call` approval callback (if wired) or is denied outright with a warning log.

**`ServerManager::execute`** (`server_manager.cpp:153-168`) — reached later, after `execute_tool` actually hands the call to the server — independently rebuilds the same pattern and checks it against `PermissionManager::deny_list_` via `is_denied`, **unconditionally**, regardless of what `check_approval` already decided:
```cpp
if (permissions_.is_denied(tool_name, pattern)) { ... return "Permission denied"; }
```
This is the documented invariant in `permission_manager.h`'s file doc: *"Deny list takes precedence over allow list."* A call that passed approval (auto-approved, allow-matched, or human-approved) can still be blocked here — deny is checked closer to execution and wins regardless of anything upstream.

## What a pattern in each list does

Both lists hold the same syntax, matched by `PermissionManager::pattern_matches` (`permission_manager.cpp:101-125`), fnmatch/glob semantics:

- A pattern is `tool_name` or `tool_name:arg_pattern`.
- The tool-name portion is always matched with `fnmatch` against the call's fully-qualified tool name (e.g. `bash.execute`, `filesystem.*`).
- If there's no `:`, tool-name match alone is sufficient.
- If there is a `:`, the *whole* pattern is matched against `tool_name + ":" + args_to_pattern(args_json)`, where `args_to_pattern` takes the first string-valued argument from the JSON args (or `*` if there are none / parsing fails).

So concretely:
- An **allow-list** entry like `bash.execute:git *` means: calls to `bash.execute` whose first argument starts with `git ` skip the approval prompt entirely (auto-approved).
- A **deny-list** entry like `bash.execute:rm *` means: any call to `bash.execute` whose first argument starts with `rm ` is blocked at dispatch time in `ServerManager::execute`, no matter what the allow list or approval callback said.

## Gap I can't close from the index

I can see that `is_explicitly_allowed`/`is_denied` are the only two call sites the index resolves for `is_allowed`/`is_denied`, and I traced the full precondition chain via AST edges (`resolved`/`exact` confidence throughout), so I'm confident this is the complete decision path for a normal tool call. I did not find the `mcp_authorization.h` file itself indexed as a queryable subject (search lists it, but `dossier` reports it "not indexed" under that exact path) — so I can describe `check_mcp_authorization`'s call into `auth_mgr_->is_enforced`/`check_access` from the caller side only; I can't hand you the internals of `MCPAuthorizationManager`'s own enforcement logic from this index without reading `mcp_authorization.h`/`.cpp` directly.
