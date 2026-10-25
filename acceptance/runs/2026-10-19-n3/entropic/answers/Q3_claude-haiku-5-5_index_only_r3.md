The index answers most of the question, but one link is inferred and one behaviour looks wrong, so check those before relying on it.

**Order of decisions for one call**

`process_single_call` (`src/mcp/tool_executor.cpp:729`) runs these in order:

1. **PRE_TOOL_CALL hook.** It can cancel the call outright ("Cancelled by hook").
2. **`check_call_preconditions`** (`tool_executor.cpp:667`), which short-circuits on the first rejection:
   - anti-spiral hard block
   - schema check
   - MCP key authorization (`check_mcp_authorization`, key tier vs. the tool's required access level)
   - tier `allowed_tools` (`check_tier_allowed`, gh#83)
   - duplicate-call detection
   - `check_approval_pc` → `check_approval` (the permission decision itself)
3. **`execute_tool`** → `ServerManager::execute`, which is where `PermissionManager::is_denied` is called (inferred from the call graph; I could not read that body).

**What `check_approval` does** (`tool_executor.cpp:161`)

```
auto_ok = loop_config.auto_approve_tools || server_manager.is_explicitly_allowed(name, args)
if !auto_ok and on_tool_call callback set:  call callback; approved = true
fire ON_PERMISSION_CHECK (informational)
return approved
```

**Problem:** when a callback is registered, `approved` is set to `true` unconditionally. The callback's return value is never read. So with a callback wired, the allow list only matters for skipping the prompt, and nothing in this function ever denies a call. That contradicts the header's claim of a default-deny model. Either the callback is meant to be a blocking prompt that returns a verdict, or the deny check happens elsewhere. I'd verify this in the code before trusting the permission model.

**What a pattern does**

Patterns are strings of the form `tool[:argpattern]`, matched with `fnmatch` (`permission_manager.cpp:101`):

- **No colon** (`filesystem.read_file`): the tool-name glob alone decides, for any arguments.
- **With a colon** (`bash.execute:pytest *`): the tool part must match, and then `tool:<args>` is matched as a whole. The args string comes from `args_to_pattern` (`server_manager.cpp:426`), which takes only the value of the **first** JSON key if it is a string, otherwise `*`. So the pattern can only see the first argument.
- `fnmatch` is called with flags 0, so `*` also matches `/`.

**The two lists**

- **allow** (`allow_list_`): `is_allowed` returns true on the first match. That skips the prompt in `check_approval`. The allow list is the only one `check_approval` consults.
- **deny** (`deny_list_`): `is_denied` returns true on the first match. Per the header, deny takes precedence over allow. The index shows `is_denied` is called from `execute`, but I could not confirm that the deny check runs before the allow shortcut.

**Persistence**

- Entries come from the `permissions:` section of the project config (`allow`, `deny`, `auto_approve`; `parse_permissions_config`, `loader.cpp:365`).
- "Always allow/deny" writes through `PermissionPersister::save_permission` (`permission_persister.cpp:227`). It adds a line like `    - bash.execute:pytest *` under `permissions.allow` or `.deny`, and does nothing if the line is already there.
- `ServerManager::add_permission` adds to the in-memory lists at runtime.
- The default per-tool pattern is the bare tool name (`MCPServerBase::get_permission_pattern`, `server_base.cpp:87`). I could not look up the `BashServer` override by name in the index.

**Not verified:** the body of `ServerManager::execute` (where deny is checked) and whether `PermissionsConfig::auto_approve` maps to `loop_config.auto_approve_tools`.