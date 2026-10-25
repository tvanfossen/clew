A tool call passes through several gates in `ToolExecutor`, and the permission lists only affect two of them. In order (`src/mcp/tool_executor.cpp`):

```
model emits call
 │
 ├─ PRE_TOOL_CALL hook ............ non-zero rc cancels the call          (857)
 ├─ anti-spiral hard block ........ projected same-tool count ≥ threshold (938)
 ├─ schema validation ............. required/enum/type vs. tool schema   (640)
 ├─ MCP key set ................... only if identity is registered;
 │                                  else allow                           (575)
 ├─ tier allowed_tools ............ exact-name list, no globs            (198)
 ├─ duplicate-call check
 ├─ check_approval()  ............. ← allow/auto_approve decide here     (161)
 │      auto_approve OR allow-list match → approved
 │      else on_tool_call set      → approved = true (see below)
 │      else                       → "Permission denied"
 ├─ execute_tool → ServerManager::execute()
 │      deny-list match → "Error: Permission denied" result             (153)
 │      else route to in-process or external server
 └─ POST_TOOL_CALL hook, history, directives
```

**What actually decides the call**

- **Deny** is checked in `ServerManager::execute` (`src/mcp/server_manager.cpp:158`), after approval. It wins over allow, but only because it is checked there. A denied call can still trigger the approval callback first.
- **Allow** is checked only in `check_approval` (`tool_executor.cpp:164`). It skips the prompt. It does not bypass the MCP key set or tier `allowed_tools`, which run earlier.
- **Approval fallthrough.** If nothing matched and the host registered `on_tool_call`, the code calls it and then sets `approved = true` unconditionally (`tool_executor.cpp:168-173`). The callback's return is never read, so it works as a notification, not a gate. Denial only happens when there is no callback and no allow match. The header comment and the "default-deny" wording in `permission_manager.h` describe something the callback path does not implement.

**What a pattern means** (`src/mcp/permission_manager.cpp:101-125`)

A pattern is split at the first `:`:

| Pattern | Matches |
|---|---|
| `filesystem.*` | Any tool whose name fnmatches; any args |
| `git.commit` | That tool, any args (no colon → name match is enough) |
| `bash.execute:python*` | `bash.execute` only when the arg pattern matches |

- The tool part is `fnmatch` against the tool name.
- The arg part is `fnmatch` against `tool_name:<arg>`, where `<arg>` is the first string-valued argument (`args_to_pattern`, `server_manager.cpp:426`). `{}` or no args becomes `*`.
- Flags are 0, so `*` also matches `/` and spaces. `bash.execute:ls*` also matches `ls; rm -rf x`.
- The per-server `get_permission_pattern` (e.g. bash's base-command extraction at `servers/bash.cpp:200`) has no callers. Permission checks never use it.
- Config comes from `permissions.allow`, `permissions.deny`, and `permissions.auto_approve` (`src/config/loader.cpp:369-371`). `PermissionPersister` and `add_permission` exist, but `set_permission_persist` is never called in `src/`, so runtime-added patterns are not persisted.

**Caveats**

- A denied tool still fires `on_tool_start` and, if a callback is registered, the approval callback, before the deny-list check returns an error result.
- I did not run anything. This is from reading the code paths, so the test suites under `tests/unit/mcp/` are the place to confirm the callback behaviour.