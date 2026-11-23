**Short answer:** a call runs only if it clears five gates in order. The allow list can skip the prompt, but the deny list is checked again at dispatch, so it still wins. With no allow match and no frontend callback, the call is refused.

## Flow

```
model emits tool call
  │
  ▼
process_single_call                        src/mcp/tool_executor.cpp:729
  ├─ PRE_TOOL_CALL hook → "Cancelled by hook"          (can veto)
  ▼
check_call_preconditions                   tool_executor.cpp:667
  ├─ anti-spiral hard block
  ├─ check_schema                          (args vs JSON schema)
  ├─ check_mcp_authorization               (not read)
  ├─ check_tier_allowed                    (locked tier's allowed_tools, gh#83)
  ├─ check_duplicate
  └─ check_approval_pc → check_approval    tool_executor.cpp:161
        approved = auto_approve_tools
                || ServerManager::is_explicitly_allowed(name, args)   ← allow list
        if !approved and on_tool_call wired:
              on_tool_call(json)  // void return, cannot veto
              approved = true                                        ← notify = approve
        if !approved → "Permission denied"
  ▼
execute_tool → ServerManager::execute      server_manager.cpp:153
  pattern = name + ":" + args_to_pattern(args)
  if permissions_.is_denied(name, pattern) → "Error: Permission denied"  ← deny list
  else route_tool_call
```

## What each list does

Both lists hold patterns, and both are matched by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`):

1. The pattern is split at its first `:`.
2. The part before the colon is `fnmatch`ed against the tool name. Without a colon, that is the whole test.
3. If there is an arg part, the full `tool:arg` string is `fnmatch`ed against the call.

| Pattern | Matches |
|---|---|
| `filesystem.*` | every filesystem tool |
| `git.commit` | that tool, any args |
| `bash.execute:python*` | bash calls whose first arg starts with `python` |

**Allow list** (`is_allowed`, checked in `check_approval`): a match means the call is approved without calling the frontend. It only skips the prompt.

**Deny list** (`is_denied`, checked only in `ServerManager::execute`): a match refuses the call even if it was approved earlier, including under `auto_approve`. The engine says it checks this first, but it runs after approval, so an allow-listed tool can still be refused at execute.

Config: `permissions: { allow: [...], deny: [...], auto_approve: bool }` (`src/config/loader.cpp:365`). "Always Allow/Deny" writes patterns back to project YAML through `PermissionPersister`.

## Things to check

- **The prompt is notify-only.** `on_tool_call` is `void (*)(const char*, void*)` (`engine_types.h:370`). Once it is wired, every call that misses the allow list is approved. The frontend cannot veto, so the security comes from the allow list and deny list, not from the user answering a prompt. Without a callback, a non-allowed call is denied. The header comment ("approved via callback") describes this behaviour, but the name suggests more gating than there is.
- **The bash "Always Allow" pattern differs from the check pattern.** `BashServer::get_permission_pattern` produces `bash.execute:<base_cmd> *`, but checks use `args_to_pattern`, which is the raw first arg, the full command string. An allow of `bash.execute:git *` therefore also matches `git status; rm -rf /`, because `*` in `fnmatch` spans shell metacharacters. I inferred this from the code and did not run it.
- **Possible fail-open on bad args (inferred, not tested).** If args don't parse, `args_to_pattern` returns `*`, so the check string is `tool:*`. A deny of `bash.execute:rm*` does not match `bash.execute:*`. Only a tool-level deny still fires. Schema checks may stop this earlier; I did not confirm that.
- **Not read:** `check_mcp_authorization` and the Python-side callback wiring. The index shows `PERMISSION_DENIED` and `ON_PERMISSION_CHECK` in `python/src/entropic/_bindings.py` but I did not open them.