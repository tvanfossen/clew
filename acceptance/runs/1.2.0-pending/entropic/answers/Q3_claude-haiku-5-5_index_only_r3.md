**Short answer:** the call runs only if it clears two gates in order. The first is an approval step in `ToolExecutor`. The second is a deny check in `ServerManager::execute`, which runs after approval and can still block the call. The deny list is never consulted during approval.

## Path of one call

```
ToolExecutor::process_single_call
  └─ check_call_preconditions(ctx, call)              tool_executor.cpp:667
       1. check_anti_spiral_hard_block   (first, always)
       2. check_schema
       3. check_mcp_authorization
       4. check_tier_allowed
       5. check_duplicate
       6. check_approval_pc → check_approval         tool_executor.cpp:161
            a. auto_ok = loop.auto_approve_tools
                         || ServerManager::is_explicitly_allowed(name, args)
            b. if !auto_ok and on_tool_call callback set → notify, approved = true
            c. fire ON_PERMISSION_CHECK (informational)
            d. not approved → "Permission denied"
  └─ route → ServerManager::execute                   server_manager.h:153
       i.  pattern = name + ":" + args_to_pattern(args)
       ii. PermissionManager::is_denied(name, pattern)  → error JSON, call never routed
       iii. route_tool_call → the server runs the tool
```

Steps 1–4 and 5 (duplicate) can reject earlier. I did not read the bodies of the anti-spiral, MCP-authorization, or tier checks, so I can't say what they decide.

## What a pattern does

Patterns come from `permissions.allow` and `permissions.deny` (`PermissionsConfig`, `config.h:589`), are parsed by `parse_permissions_config` (`loader.cpp:365`), and are held by `PermissionManager`.

- **Form:** `tool` or `tool:argpattern`. Both halves are `fnmatch` globs with no `FNM_PATHNAME`, so `*` also matches `/` and spaces.
- **Tool-only (no colon):** matches the tool name alone, so it covers every call to that tool.
- **With a colon:** the tool part must match the tool name. The full pattern must then match `tool:<arg>`, where `<arg>` is what `args_to_pattern` produces.
- **What `<arg>` is:** the value of the first string-valued argument in the JSON object. It is `*` when the args are empty, unparseable, or the first value is not a string. So `*` as the arg part matches everything.
- **Allow list:** a match skips the prompt and passes approval.
- **Deny list:** a match blocks the call at `execute`. It is checked after approval, so it overrides both allow entries and `auto_approve_tools`.
- **Bash:** `BashServer::get_permission_pattern` (`bash.cpp:200`) builds `bash.execute:<base_cmd> *`, for example `bash.execute:pytest *`. The approval check, however, keys on the first argument through `args_to_pattern`. Both forms work against an allow entry of that shape because `*` matches the rest of the command.
- **Persistence:** `save_permission` (`permission_persister.cpp:227`) writes a pattern into the project YAML under `permissions.allow` or `permissions.deny`. It is a no-op if the pattern is already present.

## Issues the index surfaced

1. **The approval callback cannot deny.** `on_tool_call` is `void(*)(const char*, void*)` (`engine_types.h:370`). In `check_approval`, a registered callback sets `approved = true` unconditionally. The "no callback → deny" branch only applies when no callback is registered. The file header and the `check_approval` brief both describe the callback as an approval gate, so the code and the docs disagree.
2. **Two auto-approve flags.** `auto_approve_tools` on the loop config and `PermissionsConfig::auto_approve` both exist. I did not trace how they connect.
3. **Wildcards cross shell metacharacters.** `bash.execute:pytest *` also matches `pytest x; rm -rf ~` under `fnmatch`. This follows from the glob semantics, not from a test.