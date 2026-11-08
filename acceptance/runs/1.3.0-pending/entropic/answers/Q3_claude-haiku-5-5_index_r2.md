**Short answer:** a tool call runs only if it survives the precondition chain in `ToolExecutor` and then `ServerManager::execute` doesn't hit the deny list. The allow list only skips the prompt. The deny list is the only hard refusal, and it is checked last. There is also a callback path that approves calls without consulting either list, which contradicts the header's default-deny description.

**The path, in order**

```
process_single_call                      tool_executor.cpp:729
 ├─ PRE_TOOL_CALL hook    → may cancel
 ├─ check_call_preconditions           :667
 │   ├─ anti-spiral hard block
 │   ├─ schema
 │   ├─ MCP authorization
 │   ├─ tier allowed
 │   ├─ duplicate-call check
 │   └─ check_approval_pc              :705  (resets dup counter)
 │        └─ check_approval            :161
 │             approved = auto_approve_tools
 │                        || ServerManager::is_explicitly_allowed (allow list)
 │             if !approved && on_tool_call set → approved = true   ← !!
 │             else → "Permission denied"
 └─ execute_tool → ServerManager::execute   server_manager.cpp:153
      ├─ is_denied(tool, tool:args)  → "Error: Permission denied for X"
      └─ route_tool_call → the server
```

1. **Hooks and preconditions** run first. A rejected call never reaches approval.
2. **Approval** (`check_approval`) passes if either `loop_config_.auto_approve_tools` is set or the allow list matches.
3. **Callback fallback.** If nothing approved the call and `on_tool_call` is registered, the code calls it and then sets `approved = true`. `on_tool_call` is a `void` callback that cannot return a refusal (`engine_types.h:370`). So any host that registers the callback to get notified of tool requests auto-approves every call that isn't allow-listed. Without a callback, unmatched calls are denied.
4. **Deny** is enforced only in `ServerManager::execute`, after approval. `is_allowed` never looks at the deny list. Deny therefore wins at execution time, but a denied call still goes through approval and any prompt first.

**What a pattern means**

`PermissionManager` (`permission_manager.cpp:101`, `pattern_matches`) splits each entry on the first `:`:

| Entry | Matches |
|---|---|
| `filesystem.*` | Every tool whose name matches the glob, any args. The part before `:` is a tool glob. |
| `git.commit` | That exact tool, any args (no colon, so args are ignored). |
| `bash.execute:python*` | `bash.execute` only when the first argument value matches `python*`. |
| `*` | Everything. |

Matching uses `fnmatch` with no `FNM_PATHNAME`, so `*` also crosses spaces and `/`. The call's arg string is built by `args_to_pattern` (`server_manager.cpp:426`), which takes the value of the first JSON key. If that value is not a string, or there are no args, it uses `*`. Two consequences:

- The "first key" is alphabetical, not the order the model wrote the arguments in. I am inferring this from nlohmann's default object type. I did not check it against a test.
- An arg pattern is a prefix match on the whole first value. `bash.execute:python*` allows `python -c ...; rm -rf …` because nothing inspects the rest of the string.

The bash "Always Allow" pattern generator (`bash.cpp:200`) produces `bash.execute:<base_cmd> *`, where the base command is the first word. That is a different shape from the first-arg match, but `fnmatch` makes it work for simple commands. I could not find a production caller for `ServerManager::get_permission_pattern`; the only caller in the index is a test. I did not confirm where persisted "always" entries are created.

**Things to check or fix**

- The callback fallback (`tool_executor.cpp`, `check_approval`) makes the default-deny doc and the `auto_approve` semantics false whenever a callback is set. Confirm whether the Python host registers `on_tool_call` in a way the user expects.
- `PermissionsConfig.auto_approve` (`types/config.h:592`) and `LoopConfig.auto_approve_tools` (`engine_types.h`) are separate fields. I did not confirm that the loader copies one into the other.
- The header comment "Deny list takes precedence over allow list" is true only because of the late check in `execute`. Moving deny into approval would stop prompting for calls that will be denied anyway.