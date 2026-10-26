The short answer: a call runs only if it clears a fixed chain of checks in `ToolExecutor`. Permission patterns come in through two lists, `allow` and `deny`. A deny match is meant to beat an allow match, and an allow match skips the approval prompt. I could not confirm the deny check's exact call site, so that part is partly inferred.

**Decision path (from `process_single_call`, `src/mcp/tool_executor.cpp:729`)**

1. `PRE_TOOL_CALL` hook fires first. If a hook cancels the call, it is rejected ("Cancelled by hook").
2. `check_call_preconditions` (`:667`) runs in this order, stopping at the first rejection:
   - anti-spiral hard block
   - schema check
   - MCP authorization
   - tier allowed
   - duplicate detection
   - approval (`check_approval_pc`)
3. `execute_tool` (`:379`) calls `ServerManager::execute`. A deny check most likely lives there, since `PermissionManager::is_denied` is called from a method named `execute`, but I could not pull that method's body to confirm it.
4. The result is recorded and the post-tool hooks fire.

**Approval step (`ToolExecutor::check_approval`, `tool_executor.cpp:161`)**

- `auto_ok` is true if `loop_config_.auto_approve_tools` is set, or if `ServerManager::is_explicitly_allowed` matches the allow list.
- If not auto-approved and an `on_tool_call` callback is registered, the callback is invoked and `approved` is set to `true` anyway. The callback is therefore a notification, not a gate.
- If no callback is registered and the call is not auto-approved, it is denied ("No approval callback — denying").

That contradicts the header comment in `permission_manager.h`, which says tools "must be explicitly allowed or approved via callback". Per the code, a registered callback approves every call it sees. Worth verifying.

**What a pattern means**

- Config keys: `permissions.allow`, `permissions.deny`, `permissions.auto_approve` (`PermissionsConfig`, `include/entropic/types/config.h:589`; parsed in `src/config/loader.cpp:365`).
- A pattern is `tool` or `tool:argpattern`, matched with `fnmatch` (`PermissionManager::pattern_matches`, `permission_manager.cpp:101`).
  - The tool part is globbed against the fully qualified tool name, e.g. `filesystem.read_file`.
  - With no `:`, the tool name alone is enough, so the pattern matches every call to that tool regardless of arguments.
  - With `:`, the arg part is globbed against `tool:<first string arg value>`. Empty or `{}` args become `*`, and unparseable JSON also falls back to `*` (`ServerManager::args_to_pattern`, `server_manager.cpp:426`).
- Default for a tool with no matching pattern is deny (default-deny), and it reaches the approval callback or is refused.
- Pattern generation for "Always Allow/Deny" is `MCPServerBase::get_permission_pattern`, which returns the bare tool name by default. `BashServer` overrides it; I could not read that override, so I don't know its granularity.
- "Always" choices persist via `PermissionPersister`, which edits `.entropic/config.local.yaml` in place.

**Gaps to check**

- The deny-precedence behaviour rests on the header comment and on the `is_denied` caller, not on a body I read.
- `ServerManager::execute` could not be fetched by name because the index has many `execute` symbols.