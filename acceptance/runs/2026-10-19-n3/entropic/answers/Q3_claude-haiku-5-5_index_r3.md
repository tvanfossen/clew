The call is decided in three places, in this order. The deny list is enforced at dispatch, not at approval, and the approval callback does not actually gate anything.

```
tool call
 │
 ├─ 1. PRE_TOOL_CALL hook          tool_executor.cpp:733   can cancel ("Cancelled by hook")
 ├─ 2. check_call_preconditions    tool_executor.cpp:667
 │      anti-spiral block → schema → MCP authorization → tier allowed_tools → duplicate
 ├─ 3. check_approval              tool_executor.cpp:161   (approval gate)
 │      approved = auto_approve_tools || allow-list match
 │      else if on_tool_call set  → approved = true (callback only notifies)
 │      else (headless)           → denied
 └─ 4. ServerManager::execute      server_manager.cpp:153  (deny gate)
        deny-list match → "Error: Permission denied for <tool>"
        else route to in-process server or external MCP client
```

**What decides it**

- **Approval (step 3)** is `auto_approve_tools` (from `permissions.auto_approve`, wired at `src/facade/entropic.cpp:1489`), or an allow-list match via `ServerManager::is_explicitly_allowed`. Anything else goes to `on_tool_call`, which returns `void`. The code sets `approved = true` immediately after calling it, so a host that shows a prompt there cannot reject the call through this path. Only a missing callback denies. The existing test "Headless mode denies without callback" covers that case.
- **Deny (step 4)** is checked only in `ServerManager::execute`, and it runs even when step 3 approved the call. So `auto_approve` plus a deny pattern still blocks the call, but the operator may see a prompt for a call that is then silently refused.

**What a pattern means**

Patterns come from `permissions.allow` and `permissions.deny` (`parse_permissions_config`, `src/config/loader.cpp:365`). `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`) works like this:

| Pattern | Split at first `:` | Matches |
|---|---|---|
| `filesystem.*` | no colon | any tool whose full name fnmatches it (all filesystem tools) |
| `bash.execute` | no colon | that one tool, any arguments |
| `bash.execute:python*` | tool=`bash.execute`, arg=`python*` | calls where the tool matches and `bash.execute:<first arg>` fnmatches the pattern |

The argument side is built by `args_to_pattern` (`server_manager.h:426`). It takes the first value of the JSON object, and uses `*` when the args are empty, unparseable, or the first value is not a string.

Three caveats follow from that code:

- **Arg patterns are prefixes, not sandboxes.** fnmatch without `FNM_PATHNAME` lets `*` match spaces and `;`, so `bash.execute:python*` also matches `python -c "…"; rm -rf ~`.
- **"First" means the first key in the object's iteration order.** I did not verify nlohmann's ordering here. If the default map is sorted, the arg being matched is the alphabetically first key, not the one the model wrote first.
- **A deny pattern with an arg suffix fails open when the first arg is not a string.** The arg then becomes `*`, which does not match `tool:rm*`.

Allow and deny both use this matcher. Allow only affects step 3. Deny is what stops a call at step 4.

**Dead or unwired pieces**

- `set_permission_persist` stores a `PermissionPersistInterface`, but nothing in `src/` calls `permission_persist_` or `PermissionPersister::save_permission`. "Always allow" does not persist yet.
- `get_permission_pattern` (per-server, e.g. the bash override) is not used by either match site. Both use `args_to_pattern`, so a server's own pattern granularity does not affect enforcement.

I did not run the test suite. These conclusions come from reading the code and the index.