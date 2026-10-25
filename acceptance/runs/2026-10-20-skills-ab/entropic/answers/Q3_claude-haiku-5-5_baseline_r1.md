The short answer: the allow and deny lists don't decide whether a call runs on their own. They are two checks at different points in a fixed pipeline, and the host callback is notify-only. Here is the path, from `ToolExecutor::process_single_call` (`src/mcp/tool_executor.cpp:729`) down to `ServerManager::execute`:

```
tool call
 │
 ├─ 1. PRE_TOOL_CALL hook          rc != 0 → denied "Cancelled by hook"
 ├─ 2. anti-spiral hard block      consecutive same-tool count ≥ threshold → denied
 ├─ 3. schema validation           missing/mistyped args → denied
 ├─ 4. MCP key authorization       identity lacks access level → denied
 ├─ 5. tier allowed_tools          locked tier's allowlist excludes tool → denied
 ├─ 6. duplicate detection         same call + args → cached result / circuit breaker
 ├─ 7. approval (check_approval)
 │      auto_approve  OR  matches allow list  → approved
 │      else, on_tool_call set                → callback fires, approved = true anyway
 │      else                                  → "Permission denied"
 ├─ 8. ServerManager::execute
 │      matches deny list → "Error: Permission denied for <tool>"
 │      else              → route to in-process or external server
 └─ 9. result, post-hook, directives
```

**Allow and deny patterns.** Both lists come from the `permissions:` section (`allow`, `deny`, `auto_approve`; `src/config/loader.cpp:365`), and can also be added at runtime with `ServerManager::add_permission`. Each pattern has the form `tool-glob` or `tool-glob:arg-glob`:

- **`tool-glob`** is matched with `fnmatch` against the fully qualified tool name, so `filesystem.*` covers every filesystem tool. A pattern with no colon matches the tool on any arguments.
- **`:arg-glob`** is matched against `tool:<first argument>`. The "first argument" is the first JSON value in the args object, and only if it is a string. Otherwise the argument part is `*`. So `bash.execute:python*` matches a bash call whose first string argument starts with `python`. Only that first argument is ever inspected.
- Matching uses `fnmatch` flags of 0, so `*` also crosses `/` and `:`.

**What each list does:**

- **Allow** (`PermissionManager::is_allowed`, reached via `check_approval`): a match skips the approval step. It is the only per-pattern way to pass step 7 without `auto_approve` or a callback. It does not bypass steps 1–6, so an allowed tool still fails schema validation, MCP key checks, or the tier allowlist.
- **Deny** (`PermissionManager::is_denied`, checked only in `ServerManager::execute`): a match returns an error tool result. The call never reaches a server. Deny runs after approval, so it wins over allow. The approval callback has already fired for a denied tool by that point.

**Things that surprised me in the code:**

1. **The approval callback cannot veto.** `on_tool_call` is declared `void (*)(const char*, void*)` (`engine_types.h:370`). After invoking it, `check_approval` sets `approved = true` (`tool_executor.cpp:168–172`). With a callback registered, every call that clears steps 1–6 runs, and the ON_PERMISSION_CHECK hook reports "allowed". The only host-side vetoes are the PRE_TOOL_CALL hook return code and the deny list.
2. **Denied calls still prompt.** Because deny is enforced later in `execute`, a deny-listed call still triggers `on_tool_call` before it is rejected.
3. **`get_permission_pattern` is dead code.** `ServerManager::get_permission_pattern` and the `BashServer` override exist, but nothing in `src/` calls them. Both the approval and deny paths build their pattern with `args_to_pattern`, so a server cannot customise the pattern it is matched against.
4. **Default is deny only when there is no callback.** With no callback and no allow match, the call is rejected. With a callback, the default flips to allow.

I read the code only and did not run the tests, so the trace above is from reading, not from an observed run.