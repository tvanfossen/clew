**Short answer:** a call runs only if it passes six gates in `ToolExecutor::check_call_preconditions`, and then `ServerManager::execute` runs the deny list. The allow list is consulted only at the approval gate. Deny is checked last, so it overrides everything before it.

## The gate order

Source: `src/mcp/tool_executor.cpp:667-694`

1. **Anti-spiral hard block.** The engine refuses a tool it has already decided to stop.
2. **Schema validation** (`check_schema`). Bad arguments are rejected.
3. **MCP key set** (`check_mcp_authorization`, line 575). This applies only if the identity has a registered `MCPKeySet`. Unregistered identities pass. This is the fail-open default described in `include/entropic/mcp/mcp_authorization.h:14-17`.
4. **Tier `allowed_tools`** (`check_tier_allowed`, line 198). If the locked tier declares a non-empty list, the tool must be in it.
5. **Duplicate detection.** Repeated identical calls are rejected, and the circuit breaker trips at three.
6. **Approval** (`check_approval`, line 161). The call is approved if either:
   - `permissions.auto_approve` is set (wired at `src/facade/entropic.cpp:1489`), or
   - `PermissionManager::is_allowed` matches the allow list.

   If neither holds and no callback is registered, the call is denied with "Permission denied".

Then `process_single_call` calls `ServerManager::execute` (`tool_executor.cpp:398`). That method (`server_manager.cpp:153-168`) runs `is_denied` against the deny list and returns "Error: Permission denied" without routing. Only if that passes does `route_tool_call` dispatch to an in-process server or external client.

## What each list does

Both lists come from YAML `permissions.allow` and `permissions.deny` (`src/config/loader.cpp:369-370`). Each entry is a pattern of the form `tool[:args]`, matched in `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`):

- **Tool part:** `fnmatch` against the fully qualified tool name, such as `filesystem.read`. `*` and `?` work as shell globs.
- **No colon:** the tool match alone is sufficient, so `bash.execute` matches every call to that tool.
- **With colon:** the full string `tool:arg` is also fnmatch'd. The argument side is built by `args_to_pattern` (`server_manager.cpp:426`), which takes the value of the first string argument, or `*` if there is none.

Behavior by list:

- **Allow:** lets the call pass approval. It does not bypass the MCP keys or tier checks that run earlier.
- **Deny:** blocks the call at execution, even if `auto_approve` is on or the allow list matches.
- **MCP key set:** a separate per-identity map of exact name, `server.*`, or `*`, with an access level (`find_best_match`, `mcp_key_set.cpp:184`). Key patterns are not fnmatch.

## Things that differ from what the names suggest

- **The callback approves everything.** In `check_approval` (`tool_executor.cpp:168-173`), if `on_tool_call` is registered and the call is not auto-allowed, the code calls the callback and then sets `approved = true`. So a host that registers the callback to "ask the user" gets a notification, not a gate. Enforcing ask-before-run requires the host to do its own blocking, or to leave the callback unset. I didn't find a path where the engine waits for an answer.
- **Deny is enforced in one place.** Only `ServerManager::execute` calls `route_tool_call`, so the deny list holds for every dispatch I could find. I didn't audit every caller of `route_tool_call`.
- **The bash-specific pattern is unused.** `BashServer::get_permission_pattern` (`src/mcp/servers/bash.cpp:200`) builds `bash.execute:<base-cmd> *`. Its only callers are tests. The live path uses `args_to_pattern`, which passes the whole command string through. So an allow entry like `bash.execute:git *` also matches `git status; rm -rf ~`, because `*` crosses `;` and `&&`. Either wire in the bash override or make the documented behavior match the code.

I traced this by reading code and did not run the test suite.