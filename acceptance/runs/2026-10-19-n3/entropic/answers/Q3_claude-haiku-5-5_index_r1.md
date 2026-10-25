A tool call passes through several gates in `ToolExecutor`, and the permission lists are only consulted at two of them. Deny is enforced later than the header comment suggests.

```
model emits tool call
  └─ ToolExecutor::process_single_call          src/mcp/tool_executor.cpp:729
      1. PRE_TOOL_CALL hook          → may cancel ("Cancelled by hook")
      2. check_call_preconditions    → src/mcp/tool_executor.cpp:667
          a. anti-spiral hard block
          b. schema check
          c. MCP key authorization   (MCPAuthorizationManager, if wired)
          d. tier allowed_tools      (gh#83, if the map is wired)
          e. duplicate-call detection
          f. check_approval_pc → check_approval          :161
               approved = (auto_approve)
                       || ServerManager::is_explicitly_allowed  ← ALLOW list
               if on_tool_call callback set → approved = true  (unconditional)
               else → "Permission denied"
      3. execute_tool → ServerManager::execute      src/mcp/server_manager.cpp:153
          └─ permissions_.is_denied(...)           ← DENY list, last
               if matched → "Error: Permission denied for <tool>"
          └─ route_tool_call → server
```

**What decides it:** the call runs only if every gate passes. The allow list and `auto_approve` are the only paths to approval. Once approval passes, the deny list is still checked in `ServerManager::execute`, so a deny match stops the call there.

**What a pattern means.** Both lists hold strings in the form `tool` or `tool:arg`, parsed by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp`):
- The part before the first `:` is an fnmatch glob against the fully-qualified tool name (for example `filesystem.*`).
- With no `:`, the tool glob alone decides the match, for any arguments.
- With a `:` part, the second glob is matched against `tool:<first-arg>`. The call's argument pattern comes from `ServerManager::args_to_pattern`, which uses the value of the first JSON key, or `*` for empty or non-string input. Example: `bash.execute:git *` matches only when the first argument value starts with `git `.
- Matching uses plain `fnmatch` with flags 0, so `*` also crosses `/` and `:`.
- Deny patterns use the same matching, and `is_denied` runs in `ServerManager::execute`.

**Things that surprised me in the code:**
1. **Deny is enforced after approval.** The header comment says "Deny list takes precedence over allow list", and that holds only at execution. If a `deny` pattern matches and the tool is also allowed, the approval callback (when set) still fires, and the result comes back as an `Error:` string from `execute`, not as a precondition rejection. So deny does not prevent a prompt.
2. **The callback approves unconditionally.** In `check_approval`, if `on_tool_call` is set, `approved = true` regardless of what the callback does, because the callback returns `void`. Under that setting, the default-deny model is effectively off. I found no facade or Python wiring that sets `on_tool_call` (only the struct field in `include/entropic/core/engine_types.h:370`), so with a stock setup the default is a plain deny.
3. **"First argument" depends on JSON key order.** nlohmann::json objects are sorted by key by default, so the "first" argument is the alphabetically first key, not the first one in the schema. I have not confirmed the parser's configuration here; check it before writing argument-scoped patterns.
4. **`auto_approve` skips the allow list entirely.** It defaults to `false` (`include/entropic/types/config.h:592`). When true, every call that passes the earlier gates is approved and the lists are not consulted for approval. Deny still applies at execution.

**Config inputs:** `permissions.allow`, `permissions.deny` and `permissions.auto_approve` are parsed in `parse_permissions_config` (`src/config/loader.cpp:365`). "Always Allow/Deny" choices are written back to project config by `PermissionPersister` (`src/storage/permission_persister.cpp:227`).

I read the code directly and did not run the tests.