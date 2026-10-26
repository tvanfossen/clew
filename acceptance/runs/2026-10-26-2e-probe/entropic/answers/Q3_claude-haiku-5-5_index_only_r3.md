**Short answer:** an allow-list match or auto-approve skips the prompt. A deny-list match blocks the call at the server boundary, after approval has already passed. Several other gates run before any of this.

```
process_single_call (tool_executor.cpp:729)
 ├─ PRE_TOOL_CALL hook            → may cancel
 └─ check_call_preconditions      (first rejection wins)
     1. anti-spiral hard block
     2. check_schema
     3. check_mcp_authorization   key/access level vs tool's required level
     4. check_tier_allowed        locked tier's allowed_tools
     5. check_duplicate           identical recent call → rejected
     6. check_approval_pc         → check_approval
           auto_approve_tools OR is_explicitly_allowed(allow list)  → run
           else if on_tool_call callback set → notify, approved = true
           else → "Permission denied"
 └─ execute_tool → ServerManager::execute (server_manager.cpp:153)
     7. permissions_.is_denied(deny list) → "Permission denied" (hard stop)
     8. route_tool_call
```

**What decides it**

- **Allow list** (`PermissionManager::is_allowed`): lets the call skip approval. It is consulted only in `check_approval`.
- **Deny list** (`PermissionManager::is_denied`): checked only in `ServerManager::execute`. It runs even if approval passed, so it is a backstop that cannot be bypassed by `auto_approve`.
- **`auto_approve_tools`**: skips the allow check and approves everything that reaches step 6.
- **Callback** (`on_tool_call`): as the body reads, it is called and `approved` is then set to `true` unconditionally. So a callback makes the call run, and the callback itself is not a gate. The header describes "approved via callback" as a gate, which contradicts this. Worth checking the wiring in the frontend before relying on it.

**What a pattern means**

- Format is `tool` or `tool:argpattern`, matched with `fnmatch`.
- `tool` alone (no colon) matches any call to that tool, e.g. `filesystem.read_file`.
- `tool:arg` matches the tool name in the tool portion, then matches the full `tool:arg` string against the arg pattern, e.g. `bash.execute:pytest *`.
- The arg value comes from `args_to_pattern`: the first string-valued field of the JSON args object, or `*` if the args are empty, unparseable, or the first field is not a string. So `bash.execute:rm *` only matches when the first string argument starts with `rm `.
- `get_permission_pattern` decides what a stored "Always Allow/Deny" rule looks like. The base class returns tool-level only. `BashServer` overrides it to produce command-level patterns.
- Both allow and deny share this syntax. Deny entries are checked with the same matcher.

**Configuration and persistence**

- `PermissionsConfig` has `allow`, `deny` (glob lists) and `auto_approve` (bool), parsed from the YAML `permissions:` section.
- `PermissionPersister::save_permission` appends a pattern to `permissions.allow` or `permissions.deny` in the project YAML. It is a no-op if the pattern is already present.

**Non-pattern gates you may not expect**

- Identity/MCP key access level (`check_mcp_authorization`) and tier `allowed_tools` (`check_tier_allowed`) both reject before approval, regardless of the allow or deny lists.
- A denied call returns a message telling the model "Do NOT retry it", so the model won't retry it.

Basis: index only. I did not verify where `on_tool_call` is wired, and I did not read the header's full "default-deny" description beyond the search brief.