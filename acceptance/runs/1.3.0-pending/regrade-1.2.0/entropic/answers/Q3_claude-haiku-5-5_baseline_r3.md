Short answer: the permission lists don't decide much on their own. A tool call passes through a fixed chain of checks in `ToolExecutor`, and the allow/deny lists only feed two of those checks. The deny list is the one real hard gate, and it runs last.

## The call path

```
ToolCall arrives
 └─ process_single_call                        tool_executor.cpp:729
     ├─ PRE_TOOL_CALL hook  → may cancel      :733
     └─ check_call_preconditions              :667  (in order)
         1. anti-spiral hard block
         2. schema validation
         3. MCP key authorization   (only if identity is enforced)
         4. tier allowed_tools
         5. duplicate-call detection
         6. check_approval_pc → check_approval  :705 / :161
              auto_ok = auto_approve_tools || is_explicitly_allowed(allow list)
              if !auto_ok and on_tool_call set  → approved = true
              else if !auto_ok                  → denied
     └─ execute → ServerManager::execute      server_manager.cpp:153
         └─ is_denied(deny list)? → return "Permission denied" JSON, no run
         └─ route_tool_call → in-process server or external MCP client
```

Any rejection stops the chain and returns a denial message to the model.

## What each list does

Patterns come from `permissions.allow` and `permissions.deny` in config (`config/loader.cpp:365`, `types/config.h:589`). They are loaded into `PermissionManager` (`mcp/permission_manager.cpp`), which is built in `ServerManager`'s constructor at `server_manager.cpp:35`. `add_permission` can add more at runtime, and the persister writes them back to config.

Each pattern has the form `tool` or `tool:argpattern`, and both halves use `fnmatch` with no flags:

| Pattern | Matches |
|---|---|
| `filesystem.*` | Any tool on the filesystem server (no `:`, so tool name only) |
| `git.commit` | Exactly that tool, any args |
| `bash.execute:python*` | `bash.execute` whose first string argument starts with `python` |
| `bash.execute:*` | `bash.execute` with any first argument |

The argument side is not the full argument list. `args_to_pattern` (`server_manager.cpp:426`) takes the value of the first JSON key, if it is a string, and otherwise uses `*`. A pattern like `bash.execute:rm*` therefore constrains only the first string argument. Because `fnmatch` runs without `FNM_PATHNAME`, `*` also matches `/` and `:`.

- **Deny list:** checked in `ServerManager::execute`, after approval. A match returns an error result and the tool never runs. The deny list is therefore enforced even when approval said yes, which makes it the one hard gate.
- **Allow list:** checked only inside `check_approval`. A match skips the approval callback. Allow does not override deny: a call that is both allowed and denied is approved, then blocked at execute time.
- **`auto_approve`:** a global switch that makes `auto_ok` true for every call. It skips the allow list but not the deny list.

## Things to know

- **The approval callback cannot veto.** `on_tool_call` returns `void`. If it is registered, `check_approval` sets `approved = true` after calling it (`tool_executor.cpp:168-172`). The "prompt" is therefore a notification, and the calling application cannot stop the call through it. The header comment at `permission_manager.h:6` says "default-deny", but that default only holds when no callback is registered. This looks like the most important gap in the chain, and I'd want to confirm it against the frontend that registers the callback.
- **Denied calls still reach the callback.** Because approval runs before the deny check, a call that is only blocked by a deny pattern still fires `on_tool_call` first.
- **MCP keys and tier rules run before the lists.** A call the identity's keys or tier `allowed_tools` reject never reaches the allow/deny lists at all.
- **The hook is advisory on approval.** `ON_PERMISSION_CHECK` fires with "allowed" or "denied" but does not change the outcome.

I traced this by reading the code and did not run the tests. `get_permission_pattern` exists on `ServerManager` but is not on the path I traced.