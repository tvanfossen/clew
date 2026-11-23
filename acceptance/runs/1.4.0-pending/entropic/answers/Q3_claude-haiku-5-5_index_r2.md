The short answer: a call runs only if it survives four checks in order. Auto-approve or the allow list is the only thing that skips prompting, and the deny list is checked last, at execution time, so it overrides everything else. One thing to know up front: the approval callback cannot refuse a call (details below).

```
config permissions {allow, deny, auto_approve}
   │  loader.cpp:365 parse_permissions_config
   │  facade entropic.cpp:1489 → loop.auto_approve_tools
   ▼
ToolExecutor::process_single_call
   │
   ├─ check_call_preconditions           tool_executor.cpp:667
   │    anti-spiral hard block → schema → MCP authorization → tier → duplicate
   │    └─ check_approval_pc             tool_executor.cpp:705
   │         └─ check_approval           tool_executor.cpp:161
   │              auto_ok = auto_approve_tools
   │                        || ServerManager::is_explicitly_allowed (allow list)
   │              if !auto_ok and on_tool_call set → fire callback, approved = true
   │              if no callback → denied ("No approval callback — denying")
   │
   ▼
ServerManager::execute                    server_manager.cpp:153
   pattern = tool + ":" + args_to_pattern(args)
   if PermissionManager::is_denied(...)  → error JSON "Permission denied", tool never runs
   else route_tool_call(...)
```

**Pattern matching** (`permission_manager.cpp:101` `pattern_matches`, plain `fnmatch`):
- The entry is split at the first `:`. The left part must match the tool name.
- With no colon, the entry matches the tool on any arguments. `git.commit` allows every `git.commit` call.
- With a colon, the right part is matched against `tool:<arg>`, where `<arg>` is the first JSON value in the arguments (`args_to_pattern`, `server_manager.cpp:426`). Empty args become `*`.

| Entry | Matches |
|---|---|
| `filesystem.*` | every tool whose name starts with `filesystem.` |
| `git.commit` | `git.commit` with any arguments |
| `bash.execute:python*` | bash commands whose command string starts with `python` |
| `bash.execute:git *` | bash commands starting with `git ` |

The same matcher serves both lists. Allow entries are consulted in `check_approval`. Deny entries are consulted in `ServerManager::execute`, so a denied call fails even if auto-approve or the callback approved it.

**Problems I found while tracing:**

1. **The approval callback cannot deny.** `EngineCallbacks::on_tool_call` returns `void` (`engine_types.h:370`). In `check_approval` (`tool_executor.cpp:168-171`), any non-null callback sets `approved = true` after it fires. So with a callback registered, every call not on the allow list runs. The header says "approved via callback", and the code does not do that. The deny list still holds.
2. **Bash allow patterns are looser than they look.** Enforcement uses `args_to_pattern`, which passes the whole command string, not the base command. `bash.execute:git *` matches `git status; rm -rf …` because `fnmatch` `*` also matches `;` and spaces. The `BashServer::get_permission_pattern` override (`bash.cpp:200`) returns the base command only, but that is used for "Always Allow" persistence, not for enforcement.
3. **"First argument" depends on key order.** I did not test this, but nlohmann::json objects iterate in key order by default, so the value used is the alphabetically first key, not the first argument the model wrote. If a tool takes several arguments, a pattern may match a different one than you expect.

I have not run any tests or changed any code.