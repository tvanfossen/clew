**Short answer:** the call runs unless it fails one of several gates in `ToolExecutor`, and the deny list is checked last, inside `ServerManager::execute`. The allow list only skips the approval prompt. It never overrides a later gate.

## The path a call takes

```
model emits ToolCall
  │
  ▼  ToolExecutor::process_single_call          src/mcp/tool_executor.cpp:729
  1. PRE_TOOL_CALL hook    → non-zero return cancels ("Cancelled by hook")
  2. check_call_preconditions                    :667
     a. anti-spiral hard block   (consecutive same-tool count)
     b. schema validation        (required / enum / type vs. tool input_schema)
     c. MCP key check            check_mcp_authorization :575
        identity = locked_tier or "lead"; no key set for identity → allow
     d. tier allowed_tools       check_tier_allowed :198 (gh#83)
     e. duplicate call           (cached result, circuit breaker at 3)
     f. approval                 check_approval :161   ← permission lists live here
  3. execute_tool → server_manager_.execute      tool_executor.cpp:398
       │
       ▼  ServerManager::execute                 src/mcp/server_manager.cpp:153
       4. is_denied(tool, pattern)  → "Error: Permission denied" result, no dispatch
       5. route_tool_call → in-process server or external MCP client
```

Step 4 is the only dispatch path. `route_tool_call` is reached only from `execute`, and `execute` is reached only from `ToolExecutor`. So the deny check cannot be skipped.

## Approval (step 2f)

```
auto_ok = config permissions.auto_approve  ||  is_explicitly_allowed(tool, pattern)
if !auto_ok and on_tool_call callback set:
    callback(json)  →  approved = true       (unconditional)
if still not approved (headless, no callback): deny "Permission denied"
```

- `permissions.auto_approve` is a global bypass. It is read from `permissions` in config (`src/config/loader.cpp:371`).
- `allow` is matched by `PermissionManager::is_allowed`. Allow entries mean "no prompt", nothing more.
- **Surprise:** `on_tool_call` is `void (*)(const char*, void*)`, so the callback cannot return a decision. Any non-null callback approves every call that isn't already allowed. The header comment ("Default-deny… approved via callback") suggests a callback can gate calls, and the code does not do that. Only a headless engine, with no callback, actually denies. `tests/unit/mcp/tool_executor_test.cpp:285` depends on this.

## Pattern syntax

Patterns are used in both `allow` and `deny` and are handled by `PermissionManager::pattern_matches` (`src/mcp/permission_manager.cpp:101`).

Format: `tool` or `tool:argpattern`. The text is split at the first `:`.

| Pattern | Matches | Effect in allow list | Effect in deny list |
|---|---|---|---|
| `bash.execute_command` | that tool, any args | skip prompt for that tool | block that tool entirely |
| `filesystem.*` | every tool on that server (fnmatch) | skip prompt for all of them | block all of them |
| `bash.execute_command:git *` | the tool, only when the arg pattern matches | skip prompt for matching args only | block matching args only |
| `*:*` | everything | skip prompt for everything | block everything |

How the arg pattern is matched:

- `args_to_pattern` (`server_manager.cpp:426`) builds the string that is matched. It takes the first entry of the args object, in nlohmann's iteration order (sorted by key by default). If that entry is a string, its value is used. Otherwise, or if args are empty or unparseable, the value is `*`.
- The full string `tool:<value>` is then fnmatch'd against the pattern. Flags are `0`, so `*` also matches `/` and `.`.

Gotchas:

- **Only the first string argument is checked.** `bash.execute_command:rm *` says nothing about a second argument such as `cwd`. Put the dangerous value first, or deny on the whole tool.
- **If the first key is non-string, the value is `*`.** A pattern like `bash:rm*` will not match that call. A `*` pattern will still match it.
- **Tool name matching is fnmatch on the fully-qualified name.** It is `server.tool`, for example `filesystem.write_file`.
- `add_permission` ignores exact duplicates. Runtime adds are persisted by `permission_persister.cpp`, which appends to `permissions.allow` / `permissions.deny`.

## Precedence

1. The PRE_TOOL_CALL hook can cancel before anything else.
2. Schema, MCP key, tier, and duplicate checks run next. Each can reject the call regardless of permissions.
3. `auto_approve` or an allow match skips the prompt. A callback approves anything else. With neither, the call is denied.
4. Deny is checked last, unconditionally. An allow match does not bypass it.

I read the code paths and the one test that exercises the headless case. I did not build or run the tests.