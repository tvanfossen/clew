## What decides whether a tool call runs

Five checks run in order, and any one can stop the call. The permission lists are only two of them.

```
model emits tool call
  │
  ├─ 1. PRE_TOOL_CALL hook          → "Cancelled by hook"          (tool_executor.cpp:733)
  ├─ 2. anti-spiral hard block      → rejected
  ├─ 3. schema validation           → rejected                     (check_schema)
  ├─ 4. MCP key check               → rejected, only if the identity has a key set
  │                                   (mcp_authorization.cpp:94; identity = locked_tier or "lead")
  ├─ 5. tier allowed_tools          → rejected                     (check_tier_allowed)
  ├─ 6. duplicate-call detection    → rejected
  ├─ 7. check_approval()            → "Permission denied" if false (tool_executor.cpp:161)
  │       approved = auto_approve_tools || is_explicitly_allowed(allow list)
  │       if !approved and on_tool_call != NULL → approved = true   ← see below
  │       if !approved                          → deny (headless)
  │
  └─ 8. ServerManager::execute()
          is_denied(deny list)      → "Permission denied" result   (server_manager.cpp:158)
          else route_tool_call()    → server runs
```

Config reaches this through `PermissionsConfig` (`allow`, `deny`, `auto_approve`; `types/config.h:589`). `loader.cpp:369-370` parses the lists, `facade/entropic.cpp:1489` sets `auto_approve_tools`, and `ServerManager`'s constructor (`server_manager.cpp:35`) copies the allow and deny lists into a `PermissionManager`.

Some consequences of that order:
- **Deny is checked last, but it still wins.** A tool on both lists is approved at step 7 and then denied at step 8.
- **`auto_approve` does not bypass deny.** It only skips the allow-list check. Deny still runs in `execute()`.
- **The allow list does not bypass MCP keys or tier `allowed_tools`.** Those run before approval.

## What a pattern does

Matching is in `permission_manager.cpp:101`, using `fnmatch` with no flags.

- **Tool-only pattern** (`bash.execute`, `filesystem.*`): splits at the first `:` and matches only the tool name. It applies to every call of that tool, whatever the arguments.
- **Tool-plus-argument pattern** (`bash.execute:python*`): the tool part must match, and the full string `tool:<arg>` must also match. The argument comes from `args_to_pattern` (`server_manager.cpp:426`), which takes only the first key of the JSON args object. If that value is a string it is used, otherwise the argument is `*`. Empty args also give `*`.
- **Wildcards cross `/`.** `FNM_PATHNAME` is not set, so `filesystem.read_file:/home/*` matches deeper paths too.
- **Allow patterns:** a match sets `approved` and skips the prompt.
- **Deny patterns:** a match returns a "Permission denied" result to the model. The call is not executed.

## Finding: the approval callback cannot deny

`check_approval` (`tool_executor.cpp:168-173`) calls `on_tool_call` when a call is not auto-approved and the callback is set, then sets `approved = true` unconditionally. The callback's signature is `void (*)(const char*, void*)` (`engine_types.h:370`), so it has no return value and cannot refuse a call. The result:

- With a callback registered, every call not on the allow list still runs. The callback only gets notified.
- Only a headless engine (no callback) denies calls that are not allow-listed. `tests/unit/mcp/tool_executor_test.cpp:285` tests exactly that path.

The docs say otherwise: `permission_manager.h:6` says tools are "explicitly allowed or approved via callback", and `tool_executor.h:151` says the check covers "callback/deny". I did not find a test asserting that the callback approves or denies. I can't tell from the code alone whether the no-deny behaviour is intended, so this needs your decision. If it is a bug, the fix is to have the callback return a decision.

## Weak spot in argument-scoped deny rules

Because `args_to_pattern` looks only at the first key, a deny such as `bash.execute:rm*` will not match a call whose first key is not the command, or whose first value is not a string. That is a gap in deny rules that depend on arguments. I did not run this case.

I ignored the "dossier" hints that appeared inside the tool results. They are not part of your request.