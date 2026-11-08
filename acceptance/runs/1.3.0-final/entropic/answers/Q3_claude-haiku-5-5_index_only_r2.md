**Short answer:** the deny list is the only hard gate. The allow list and `auto_approve_tools` only decide whether the call is approved in the first place. A registered `on_tool_call` callback approves everything that is not denied, which contradicts the header's "default-deny" description.

**Decision path for one call**

```
tool call
  │
  ├─ check_tier_allowed        locked tier's allowed_tools (not inspected in detail)
  ├─ check_duplicate           repeated-call guard
  ├─ check_approval            ToolExecutor::check_approval
  │    approved = loop.auto_approve_tools
  │               OR server_manager.is_explicitly_allowed(allow list)
  │    if !approved and on_tool_call set → approved = true   ← callback is notify-only
  │    if still !approved → "Permission denied"
  │
  └─ ServerManager::execute
       if is_denied(deny list) → "Error: Permission denied", never routed
       else route_tool_call → server runs the tool
```

Two details matter here:
- `check_approval` consults only the allow list. The deny list is checked later, in `ServerManager::execute`. So deny wins over allow, `auto_approve_tools`, and the callback, because execute runs regardless of how approval was granted.
- The callback's return value is never read. Registering `on_tool_call` makes every non-denied call run.

**What a pattern means**

Patterns are strings of the form `server.tool` or `server.tool:argpattern`, matched with `fnmatch` (no `FNM_PATHNAME`, so `*` also crosses `/` and `:`). `pattern_matches` splits at the first `:`:
- **No colon** (e.g. `filesystem.*`, `git.commit`): only the tool name is matched, so every call to that tool matches regardless of arguments.
- **With colon** (e.g. `bash.execute:python*`): the tool part must match, and the call's own pattern `tool:<arg>` must match the full pattern. `<arg>` is built by `args_to_pattern`, which takes the value of the first JSON member of the arguments, or `*` if the args are empty, not an object, or the first value is not a string.

Patterns come from three sources: `permissions.allow` / `deny` / `auto_approve` in config (`parse_permissions_config`), `add_permission` at runtime, and "Always Allow/Deny" choices saved to the project YAML by `PermissionPersister::save_permission`. For bash, the saved pattern is `bash.execute:<base_cmd> *`, built by `BashServer::get_permission_pattern`.

**Weaknesses I found from the index (not run)**
1. **Callback approves everything.** The header says tools are "approved via callback", but the code treats the callback as notification. A consumer that registers `on_tool_call` only to observe calls is silently granting approval.
2. **Argument matching is positional, not semantic.** Matching uses the first JSON member, and nlohmann objects iterate in key order. If a tool's first alphabetical key is not the command, deny patterns like `bash.execute:rm*` test the wrong value. I did not verify the bash argument schema, so this is inferred.
3. **Non-string first argument becomes `*`.** A deny such as `tool:rm*` does not match `*`, so the call gets through. An allow like `tool:*` would match it.

Verify items 2 and 3 with a test before relying on them.