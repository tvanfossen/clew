**Short answer:** a call runs only if it clears a fixed sequence of checks in `ToolExecutor`. Approval is the only check that consults the permission lists, and deny is enforced later, inside `ServerManager::execute`. One part of the approval step does not match the documented default-deny model (see the callback note below).

**Flow for one call** (`src/mcp/tool_executor.cpp`, `process_single_call` at :729)

```
PRE_TOOL_CALL hook ──cancel?──► denied ("Cancelled by hook")
        │
check_call_preconditions (:667), in order:
  1. anti-spiral hard block        (:938)
  2. schema validation             (:640)
  3. MCP key set for identity      (:575)
  4. tier allowed_tools            (:198)
  5. duplicate-call check          (:117)
  6. approval  check_approval()    (:161)  ◄── only step that reads the permission lists
        │ pass
execute_tool → ServerManager::execute (server_manager.cpp:153)
  7. deny list  is_denied()  ──match──► "Error: Permission denied for <tool>"
        │ pass
  route to in-process server or external MCP client
```

**What `check_approval` does** (:161–188)

- Approved if `loop_config_.auto_approve_tools` is set (from `permissions.auto_approve`, facade `entropic.cpp:1489`), or if `is_explicitly_allowed()` matches the allow list.
- Otherwise, if the consumer registered an `on_tool_call` callback, the callback is fired and `approved = true` is set at :172.
- With no callback, the call is denied with "Permission denied".

**Caveat:** because the callback sets `approved = true` unconditionally, the default-deny described in `permission_manager.h` only holds for consumers with no `on_tool_call` callback. For any consumer that wires one, the allow list has no effect on approval, and only the deny list gates execution. I did not run tests to confirm this is unintended, but the code is clear.

**Where the lists come from**

- `permissions.allow`, `permissions.deny` and `permissions.auto_approve` are parsed from YAML in `config/loader.cpp:365–373`.
- They are copied into `PermissionManager` when `ServerManager` is constructed (`server_manager.cpp:32–36`, called from `facade/entropic.cpp:792`). Later config edits do not affect it. `add_permission()` changes it at runtime.

**What a pattern means**

Both lists use the same matcher (`permission_manager.cpp:101–125`):

| Pattern form | Matches |
|---|---|
| `filesystem.*` | Any call whose tool name matches the glob. Argument values are ignored. |
| `bash.execute:python*` | Tool name matches the part before `:`, and `tool:<value>` matches the full pattern. |

- The value is `args_to_pattern()` (`server_manager.cpp:426`): the first argument in the JSON object whose value is a string, or `*` if there is none. nlohmann's default object type sorts keys, so "first" means alphabetically first, not first in the call. If that first key is not a string, the value is `*`.
- `fnmatch` runs with flags 0, so `*` also matches `/` and `:`.
- Allow patterns only skip the approval prompt. Schema, MCP-key and tier checks still run first and can still reject the call.
- Deny patterns are checked in `execute()` after approval, so a tool that is both allowed and denied is still blocked. Deny wins.
- A denied call returns an error result to the model. It does not stop the loop.

**Dead code to note:** `BashServer::get_permission_pattern()` (`bash.cpp:200`) would build `bash.execute:<base> *`, but nothing calls it. Matching always uses `args_to_pattern()`. The documented `bash.execute:python*` form works. Any pattern written with the `base *` shape would not match the way that method suggests.