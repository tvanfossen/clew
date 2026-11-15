## Short answer

Two layers decide a call, in this order: the **approval gate** (`check_approval`) and the **deny check** (`ServerManager::execute`). The allow list only skips the prompt. The deny list is the only thing that can block an approved call. There's a caveat on the prompt path, covered below.

## Trace

```
model emits tool call
 └─ ToolExecutor::process_single_call              tool_executor.cpp:729
     ├─ PRE_TOOL_CALL hook                         can cancel ("Cancelled by hook")
     ├─ check_call_preconditions                   :667, in order:
     │    1. anti-spiral hard block
     │    2. schema validation (check_schema)
     │    3. MCP key auth (check_mcp_authorization :575)  only if identity is enforced
     │    4. tier allowed_tools (gh#83)            rejected_unauthorized
     │    5. duplicate-call detection
     │    6. check_approval_pc → check_approval     :161
     │         a. auto_approve_tools (permissions.auto_approve)  OR
     │            ServerManager::is_explicitly_allowed → allow list match
     │         b. else, if on_tool_call callback is set → invoke it, approved = true
     │         c. else → "Permission denied" (headless / default-deny)
     ├─ execute_tool → ServerManager::execute      server_manager.cpp:153
     │    └─ is_denied(tool, pattern)? → "Error: Permission denied for X"
     │    └─ route_tool_call → in-process server or external MCP client
     └─ PRE/POST hooks, result
```

Config feeds this: `PermissionsConfig { allow, deny, auto_approve }` (`include/entropic/types/config.h:589`) is parsed in `config/loader.cpp:365`. `allow` and `deny` go into `PermissionManager` via the `ServerManager` constructor (`server_manager.cpp:35`), and `auto_approve` goes into `LoopConfig` (`facade/entropic.cpp:1489`).

## What a pattern does

Patterns are `tool` or `tool:argpattern`, matched with `fnmatch` (`permission_manager.cpp:101`):

- The text before the first `:` is matched against the fully-qualified tool name.
- With no `:`, the tool match is enough.
- With a `:`, the text after it is matched against `tool:<arg value>`. The arg value comes from `args_to_pattern` (`server_manager.cpp:426`), which takes only the first key of the args object if that value is a string. Otherwise it is `*`.

| Pattern | Effect |
|---|---|
| `filesystem.*` | Any filesystem tool |
| `bash.execute:python*` | `bash.execute` whose first string arg starts with `python` |
| `git.commit` | Exactly that tool, any args |
| `bash.*` in **deny** | Blocks every bash call, even if `bash.execute` is also allowed |

Two details to note:

- `args_to_pattern` uses nlohmann's object iteration order, which is alphabetical by key, not the order the model wrote the args. For a call with `{"path":…, "content":…}`, the first key checked is `content`. Arg-level patterns depend on that.
- Since `fnmatch` runs without `FNM_PATHNAME`, `*` also matches `/`. So `filesystem.read_file:/home/*` matches deeper paths too.

## What the lists do

- **Allow** (`is_allowed`) only sets `auto_ok` in `check_approval`. It does not bypass the later deny check.
- **Deny** (`is_denied`) runs in `ServerManager::execute` after approval, so it wins over allow. Its result comes back as a tool error, not a rejection.
- Both lists can be extended at runtime with `add_permission`. `ALWAYS_ALLOW`/`ALWAYS_DENY` are persisted through `PermissionPersister`.

## Caveat: the prompt does not gate

In `check_approval` (`tool_executor.cpp:168-173`), if a callback is set the code invokes it and then sets `approved = true` unconditionally. `on_tool_call` returns `void` (`engine_types.h:370`), so the engine never reads a user's DENY back. The `ToolApproval` enum (`engine_types.h:63`) exists, but I didn't find code in this tree that turns a user's answer into a return value for `check_approval`.

In practice, with a callback installed, the only things that stop a call are:
- deny-list matches,
- the MCP key, tier, schema, and duplicate checks upstream.

Without a callback and without an allow match, calls are denied (`tests/unit/mcp/tool_executor_test.cpp:280`).

I haven't run the test suite. This is from reading the code. If you want, I can check how the Python/TUI layer uses `on_tool_call` to confirm whether it expects a blocking reply.