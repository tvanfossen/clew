A tool call is decided in two places. Approval happens in the executor before dispatch, and the deny list is checked later, inside `ServerManager::execute`. The allow list only affects approval; it never overrides the deny list.

**Trace for one call** (`src/mcp/tool_executor.cpp:729` `process_single_call`)

1. **PRE_TOOL_CALL hook** (`:857`). A plugin hook returning nonzero cancels the call with "Cancelled by hook". This runs before everything else.
2. **Precondition chain** (`:667` `check_call_preconditions`), first rejection wins:
   - Anti-spiral hard block (`:938`): too many consecutive calls to the same tool.
   - Schema check (`:640`): args validated against the tool's `input_schema`.
   - MCP key authorization (`:575`): only enforced when the identity (locked tier, or `lead`) has a key set.
   - Tier `allowed_tools` (`:198`, gh#83).
   - Duplicate check (`:117`): a repeat of a cached call returns the old result without approval.
   - **Approval** (`:161` `check_approval`, via `:705`):
     - Approved if `auto_approve_tools` is set, or the call matches the allow list (`ServerManager::is_explicitly_allowed` → `PermissionManager::is_allowed`).
     - Otherwise, if the host registered `on_tool_call`, that callback is invoked and the call is approved anyway (`:168-172`). The callback is a notification, not a gate.
     - Otherwise it is denied with "Permission denied" (`:185`).
3. **Execute** (`src/mcp/server_manager.cpp:153`). `is_denied()` is checked on the deny list. A match returns `Error: Permission denied for <tool>` as a tool result. This runs even when approval passed via `auto_approve` or the allow list.
4. Route to the in-process server or external MCP client.

**What a pattern is**

A pattern is `tool` or `tool:argpattern` (`permission_manager.cpp:101`).
- The part before the first `:` is matched with `fnmatch` against the tool name.
- If there is no `:`, that match is enough, so the rule covers every argument set.
- If there is a `:`, the full `tool:argpattern` is `fnmatch`ed against `tool_name + ":" + args_to_pattern(args)`.

`args_to_pattern` (`server_manager.cpp:426`) does not look at all arguments. It takes the value of the first key in the parsed JSON object, and only if that value is a string. Otherwise it uses `*`. nlohmann's object iteration is key-sorted, so "first" means alphabetically first. Under the arg-pattern case, `*` also matches `/` and `:`.

| Pattern | Effect |
|---|---|
| `filesystem.*` | Any filesystem tool, any args |
| `bash.execute` | `bash.execute` with any args |
| `bash.execute:python*` | Only when the alphabetically-first string arg starts with `python` |
| `bash.execute:*` or `tool:*` | Any args, same as no suffix (empty args also become `*`) |

Because only one argument is checked, a pattern like `filesystem.write:/safe/*` can be bypassed or misfire if the alphabetically-first string arg is not the path. I did not check which argument names the built-in tools use, so I have not confirmed that case.

**Where the lists come from**

- `permissions.allow`, `permissions.deny`, `permissions.auto_approve` in YAML (`src/config/loader.cpp:365`).
- Runtime `add_permission` (`permission_manager.cpp:79`), which skips exact duplicates.
- Stored lists are written back by the permission persister (`src/storage/permission_persister.cpp`). I did not trace what it writes.

**Problems I noticed**

- The header says default-deny with "approved via callback" (`include/entropic/mcp/permission_manager.h:6`). The code is default-deny only when no `on_tool_call` callback is registered. With a callback, every non-allow-listed call is approved (`tool_executor.cpp:168-172`). If the host expects the callback to be able to refuse, that is not what happens. I did not check whether the facade's callback blocks for a user decision, so whether this is exploitable depends on the host.
- Deny is enforced only at execute time, so a denied call still goes through the approval callback first. A user may be prompted for a call that is then refused.