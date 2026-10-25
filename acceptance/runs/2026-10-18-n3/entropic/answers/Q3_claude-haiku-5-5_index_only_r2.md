The short answer: the call runs only if it clears a fixed sequence of checks in `ToolExecutor`, and the deny list is re-checked at dispatch, so it can stop a call that was already approved. One thing looks wrong: with a host callback registered, approval is granted without reading the callback's answer. I got all of this from the index's verbatim bodies, not from running anything.

```
model emits tool call
  └─ ToolExecutor::process_single_call          (tool_executor.cpp:729)
      1. fire_pre_tool_hook          → hook can cancel ("Cancelled by hook")
      2. check_call_preconditions    (tool_executor.cpp:667), first failure wins:
           a. anti-spiral hard block
           b. check_schema
           c. check_mcp_authorization  → MCP key access level (identity = locked_tier or "lead")
           d. check_tier_allowed       → tier allowed_tools (gh#83)
           e. check_duplicate          → duplicate-call handling
           f. check_approval_pc → check_approval (tool_executor.cpp:161):
                auto_approve_tools            → approved
                or ServerManager::is_explicitly_allowed (allow list) → approved
                or on_tool_call callback present → approved = true  (return value ignored)
                else → "Permission denied"
      3. execute_tool → ServerManager::execute   (server_manager.cpp:153)
           a. pattern = tool + ":" + args_to_pattern(args)
           b. permissions_.is_denied(...)  → "Error: Permission denied" (deny always wins)
           c. route_tool_call → MCP server
```

**What decides it**

- **Allow list alone** does not run a call. It skips the interactive approval step (2f). Auth, tier, schema and duplicate checks still apply.
- **`auto_approve_tools`** (`LoopConfig`) also skips approval, but not the deny check in step 3b. It is a separate flag from `PermissionsConfig.auto_approve`, and the index does not show how the two are wired.
- **Deny list** is checked in `ServerManager::execute` regardless of approval, so a denied pattern blocks even under auto-approve. It is the last gate before the server runs.

**What a pattern means**

- Format is `tool` or `tool:argpattern`, e.g. `bash.execute:pytest *`.
- `args_to_pattern` takes the value of the first string argument in the JSON. It returns `*` for empty args, a non-object, or a parse failure. The call is matched as `tool:<that value>`.
- `pattern_matches` (`permission_manager.cpp:101`) uses `fnmatch` on the tool part first. A pattern with no colon matches every call to that tool. A pattern with a colon must also match the full `tool:arg` string.
- Matching is glob-based and ignores argument structure. `bash.execute:ls*` matches any command beginning with `ls`, including `ls; rm -rf x` if the first argument is that string.
- The default `MCPServerBase::get_permission_pattern` returns the bare tool name. Its only indexed callers are tests and its own destructor, so it does not feed the matching path. `BashServer` overrides it, but I could not read that body through the index.

**Persistence**

- `ToolApproval` has `ALLOW`, `DENY`, `ALWAYS_ALLOW`, `ALWAYS_DENY`.
- `PermissionPersister::save_permission` writes a pattern into `permissions.allow` or `permissions.deny` in the project YAML, skipping it if already present.
- I did not trace how a `ToolApproval` answer reaches `save_permission` or the in-memory lists.

**Concerns**

1. **Callback ignores the answer.** If `on_tool_call` is set, `check_approval` sets `approved = true` without consulting it. A host that uses that callback to ask the user would not block anything through this path. Check the host side before relying on it.
2. **First-argument matching.** `args_to_pattern` takes the first JSON key. If that is alphabetical rather than call order (which I believe nlohmann does by default, from memory, not the index), the pattern binds to a different argument than the author expects. This needs confirming.