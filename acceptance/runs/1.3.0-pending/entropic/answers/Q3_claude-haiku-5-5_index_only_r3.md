The short answer: a call runs only if it clears two separate gates, and the deny list is enforced at the second one, after approval has already happened. I answered from the index alone, so I did not read the YAML loader or the code that maps the `permissions.auto_approve` config key to `LoopConfig.auto_approve_tools`.

**Flow**

```
model emits tool call
  │
  ▼  ToolExecutor::check_call_preconditions   (tool_executor.cpp:667)
  │   1. anti-spiral hard block
  │   2. schema check
  │   3. MCP authorization
  │   4. tier allowed_tools (gh#83)
  │   5. duplicate-call detection
  │   6. check_approval_pc → check_approval      ◄── ALLOW list lives here
  │        approved if:  loop_config.auto_approve_tools
  │                   OR server_manager.is_explicitly_allowed(tool, args)
  │                   OR on_tool_call callback is wired (always sets approved=true)
  │        otherwise:   "Permission denied", logged as warning
  ▼
  ServerManager::execute                       (server_manager.cpp:153)
  │   pattern = tool + ":" + args_to_pattern(args)
  │   if permissions_.is_denied(tool, pattern)  ◄── DENY list lives here
  │        return {"result": "Error: Permission denied for <tool>"}
  ▼
  route_tool_call → server runs
```

**What a pattern does**

Patterns are matched by `PermissionManager::pattern_matches` using `fnmatch`, with no `FNM_PATHNAME`, so `*` also matches spaces and slashes.

| Pattern | Matches |
|---|---|
| `filesystem.*` | Every call to any tool whose name matches the glob. No colon, so args are ignored. |
| `git.commit` | Only that exact tool, any args. |
| `bash.execute:python*` | Tool part `bash.execute` must match, and the first argument value must match `python*`. |
| `bash.execute:pytest *` | What "Always Allow" saves for bash (`BashServer::get_permission_pattern`). The `*` matches the rest of the command line. |

The argument value comes from `args_to_pattern`. It is the value of the first key in the args JSON object if that value is a string. Empty args, `{}`, an unparseable body, or a non-string first value all become `*`.

**What this means in practice**

- **Allow list:** `is_allowed` returns true on the first matching pattern. A match only skips the approval prompt. It does not bypass the deny check.
- **Deny list:** `is_denied` runs in `ServerManager::execute` on every call, including calls the user approved in the callback. A tool that is both allowed and denied is blocked. The denial comes back as an error result string, not through the normal denial message path.
- **Default posture:** The header says "default-deny," but that holds only when no approval callback is wired. With a callback, `check_approval` sets `approved = true` after calling it, and the callback's return value is not read. The callback can notify but cannot veto, so the deny list is the only real veto in that configuration.
- **Persistence:** `PermissionPersister::save_permission` appends the pattern to `permissions.allow` or `permissions.deny` in `config.local.yaml`. I did not confirm whether saving also calls `add_permission` on the live manager.

**Risks I found reading the code**

1. **Argument-scoped deny is bypassable.** A deny like `bash.execute:rm *` is only checked against the first argument value. If the first key is non-string, or the args are malformed or `{}`, the pattern becomes `bash.execute:*`, which does not match `rm *`. The deny misses. Whether a real `bash` call can produce this depends on the argument shape, which I did not verify.
2. **Bash persistence patterns are loose.** The saved `bash.execute:pytest *` also matches `pytest x; rm -rf ~`, because `*` matches anything after the prefix.
3. **Two sources of truth for bash.** The bash override `get_permission_pattern` builds the string that gets saved. Matching uses `args_to_pattern`, which is different. The index shows no call from `execute` to `get_permission_pattern`, so I could not confirm that persisted bash patterns match as the user expects.