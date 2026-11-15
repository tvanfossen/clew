**What decides whether a call runs:** the permission lists alone don't. The path is `ToolExecutor` (`src/mcp/tool_executor.cpp`), then `ServerManager` (`src/mcp/server_manager.cpp`), then `PermissionManager` (`src/mcp/permission_manager.cpp`).

```
model emits tool call
 └─ check_call_preconditions            tool_executor.cpp:667
     1. anti-spiral hard block
     2. schema validation               (check_schema)
     3. MCP key authorization           (check_mcp_authorization, identity keys, not the lists)
     4. tier allowed_tools              (gh#83)
     5. duplicate-call detection
     6. check_approval_pc → check_approval   tool_executor.cpp:161
          auto_ok = permissions.auto_approve
                    OR is_allowed(name, "name:" + args_to_pattern(args))
          if !auto_ok and on_tool_call set → approved = true   (line 172, unconditional)
          if !auto_ok and no callback      → denied "Permission denied"
 └─ dispatch: ServerManager::execute     server_manager.cpp:153
     pattern = name + ":" + args_to_pattern(args)
     is_denied(name, pattern) → "Error: Permission denied for <tool>"
     else route_tool_call → in-process server or external MCP client
```

**What a pattern means** (`pattern_matches`, `permission_manager.cpp:101`):

- The text before the first `:` is an fnmatch glob matched against the fully-qualified tool name, e.g. `filesystem.*` or `git.commit`. No colon means a tool-only match.
- If there is a colon, the whole `tool:arg` pattern is fnmatch'd against `tool:<argvalue>`, e.g. `bash.execute:python*`.
- Flags are 0, so `*` also crosses `/`.
- Lists are OR'd and first match wins; order does not matter.
- `deny` is checked only in `execute`. `allow` is checked only in `check_approval`. Neither list is checked in the other place.

**Things that will surprise you:**

1. **`args_to_pattern` (`server_manager.cpp:426`) uses only one argument.** It takes the first key in nlohmann's object iteration order. That is alphabetical, because the default object type is `std::map`, not call order. Only a string value is used; anything else becomes `*`. So for `write_file` with `{"content":…,"path":…}`, a rule like `filesystem.write_file:/etc/*` tests `content`, not `path`. I did not run this, so treat it as a code-reading conclusion.
2. **The bash pattern builder is not on the checked path.** `BashServer::get_permission_pattern` (`bash.cpp:200`) produces `bash.execute:<base> *`, but nothing in `src/` calls it on the approval or deny path. Bash rules are therefore matched against the raw command string. `bash.execute:pytest *` matches `pytest -q && rm -rf x`, because `*` spans shell metacharacters. It does not match bare `pytest`.
3. **The callback is not a gate.** The header says tools are "explicitly allowed or approved via callback" and default-deny. The code notifies the callback and then sets `approved = true` without reading any return value. Without a callback, unlisted tools are denied. With one, every call passes approval. Deny-list entries still block at `execute`, but only after the callback has already reported the call.
4. **`auto_approve: true` does not skip deny.** `execute` still checks `is_denied`, so deny always wins over allow and over auto-approve.

Config comes from the `permissions:` section (`config/loader.cpp:365`), which feeds `ServerManager`'s constructor. `PermissionPersister` writes `allow:`/`deny:` entries to `config.local.yaml`; I did not trace which UI path calls it.

I read the code and did not run the tests or a live call, so the behaviour above is from reading.