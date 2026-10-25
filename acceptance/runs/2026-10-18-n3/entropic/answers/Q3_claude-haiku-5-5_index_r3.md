A tool call passes through several gates in `ToolExecutor` before it runs. The permission lists only feed two of them. The allow list can skip the prompt, and the deny list is checked later, at dispatch.

```
model emits tool call
  │
  ▼  ToolExecutor::check_call_preconditions  (tool_executor.cpp:667)
  1. anti-spiral hard block
  2. schema validation             (check_schema)
  3. MCP key authorization         (check_mcp_authorization :575)
  4. tier allowed_tools            (check_tier_allowed :198)
  5. duplicate detection
  6. approval                      (check_approval :161)
  │     auto_approve_tools?  ──yes──► approved
  │     allow list match?   ──yes──► approved
  │     on_tool_call cb set? ─yes──► approved (see caveat)
  │     otherwise                 ──► "Permission denied"
  ▼
  ServerManager::execute  (server_manager.cpp:153)
  7. DENY list match?  ──yes──► "Error: Permission denied for <tool>"
  ▼
  route_tool_call → in-process server or external MCP client
```

**What decides the call:** the first gate that rejects it wins. The permission lists only matter at steps 6 and 7. Steps 3 and 4 can reject a call that the allow list would otherwise approve.

**The lists**

- `permissions.allow` and `permissions.deny` come from YAML via `parse_permissions_config` (`src/config/loader.cpp:365`). They land in `PermissionsConfig` (`include/entropic/types/config.h:589`), alongside `auto_approve`.
- `ServerManager` copies both lists into a `PermissionManager` at construction (`server_manager.cpp:35`).
- `permissions.auto_approve` becomes `LoopConfig.auto_approve_tools` (`src/facade/entropic.cpp:1489`), which skips the prompt entirely.

**What a pattern does** (`permission_manager.cpp:101`)

Each call is turned into a string `tool:firstArg`. `args_to_pattern` (`server_manager.cpp:426`) takes the first string-valued argument, or `*` when there are no args or the first value is not a string. A pattern is then split at the first `:`:

| Pattern | Tool part | Arg part | Matches |
|---|---|---|---|
| `filesystem.*` | `filesystem.*` | none | every filesystem tool, any args |
| `git.commit` | `git.commit` | none | that tool, any args |
| `bash.execute:python*` | `bash.execute` | `python*` | bash calls whose first argument starts with `python` |

- Both halves use `fnmatch`, with no flags. `*` also matches `/`.
- With no colon, the tool name alone decides the match.
- With a colon, the tool name must match and the full `tool:arg` string must match too.
- Lists are checked in order, first match wins. A deny match is logged as `Permission DENIED`, and an allow match as `Permission ALLOWED`.

**Things to know**

- Deny beats allow in practice. A call on the allow list still reaches `ServerManager::execute`, where the deny list is checked again. So a tool that is both allowed and denied is blocked. The header comment says the same (`permission_manager.h:6`).
- Deny is checked late. A denied tool still gets through the approval step, and the `ON_PERMISSION_CHECK` hook reports it as `allowed` in that case (`tool_executor.cpp:177`). That makes the hook misleading for denied calls.
- The callback cannot veto. `on_tool_call` returns `void` and `approved` is set to `true` right after it is called (`tool_executor.cpp:168-172`). Whether a user actually blocks a call depends on what the consumer does inside that callback, which I did not trace.
- Only the allow list is consulted at approval. `is_explicitly_allowed` (`server_manager.cpp:286`) checks only `permissions_.is_allowed`.
- "Always Allow/Deny" writes the pattern into the YAML `allow:`/`deny:` lists via `PermissionPersister::save_permission` (`permission_persister.cpp:227`). It is also added to the in-memory list through `add_permission`.

I read the source directly for this. The index had `dossier` results for the pattern and config symbols, but not for `ToolExecutor::check_approval` or `ServerManager::execute`.