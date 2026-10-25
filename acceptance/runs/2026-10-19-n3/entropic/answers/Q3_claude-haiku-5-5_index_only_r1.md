Short answer: a call runs only if it clears a fixed chain of checks in `ToolExecutor`, and the allow and deny lists are only consulted in two of those steps. I traced this from the index alone, so the one link I could not read directly is flagged below.

**Decision path for one tool call**

```
process_single_call
 └─ check_call_preconditions            (tool_executor.cpp:667)
     1. check_anti_spiral_hard_block    → reject (rejected_anti_spiral)
     2. check_schema                    → reject (rejected_schema)
     3. check_mcp_authorization         → reject (MCP key/identity)
     4. check_tier_allowed              → reject (tier allowed_tools / bash_commands, gh#83)
     5. check_duplicate                 → reject (rejected_duplicate)
     6. check_approval_pc → check_approval   (tool_executor.cpp:161)
          auto_ok = loop_config.auto_approve_tools
                    || server_manager.is_explicitly_allowed(name, args)
          if !auto_ok and on_tool_call callback set → approved = true
          if still not approved                    → "Permission denied"
 └─ ServerManager::execute
      permissions_.is_denied(name, pattern)  → error JSON, tool not run
      else route to in-process or external server
```

Points that matter:

- **Allow is checked at step 6, deny at execute.** `check_approval` only looks at the allow list. The deny list is checked later, inside `ServerManager::execute`, which the call graph shows calling `is_denied`. So a deny match stops the call even when `auto_approve` is on or the tool is allow-listed. I could not read `ServerManager::execute`'s body through the index (the qualified lookup failed), so that the deny check happens there rests on the graph edge and the header's "deny takes precedence" doc.
- **The approval callback does not gate.** In `check_approval`, if the callback is registered, `approved` is set to `true` after the callback is invoked, without using its return value. Its only gating effect is that without a callback, an unlisted call is denied. The header calls the callback an approval path, so this is a possible discrepancy worth checking against the header's contract.
- **Tier and duplicate checks sit before approval.** A call can be refused by the tier `allowed_tools` map or as a duplicate before any allow-list is read.

**What a pattern in each list does**

Patterns are `fnmatch` globs in `PermissionManager` (`src/mcp/permission_manager.cpp`):

- **Form:** `tool` or `tool:args`. The tool part is matched against the fully qualified name, e.g. `bash.execute`.
- **`tool` alone:** matches that tool with any arguments.
- **`tool:args`:** the args part is matched against `tool:<first>`, where `<first>` is the first string-valued argument (`ServerManager::args_to_pattern`). Empty or unparseable args become `*`. Example: `bash.execute:pytest *` matches a call whose first argument is `pytest …`.
- **Globs are not path-aware.** `fnmatch` is called without `FNM_PATHNAME`, so `*` also crosses `/`.
- **Deny entries** use the same syntax and are checked with the same matcher. A match logs "Permission DENIED" and blocks the call.
- **Allow entries** match the same way and log "Permission ALLOWED". They only skip the prompt; they do not run the tool by themselves.
- **Granularity** is set per server. The default `get_permission_pattern` returns the bare tool name, so an "Always Allow" grants the whole tool. `BashServer` overrides it to produce finer patterns.

**Where the lists come from**

- Config `permissions:` has `allow`, `deny` (string lists) and `auto_approve` (bool). The README uses `permissions.auto_approve: true` to skip prompts.
- At runtime, "Always Allow/Deny" writes new patterns into `config.local.yaml` through `PermissionPersister::save_permission`, deduplicated and under a mutex.

I could not confirm how `permissions.auto_approve` is wired to `loop_config.auto_approve_tools`; I'm inferring that it is the same flag.