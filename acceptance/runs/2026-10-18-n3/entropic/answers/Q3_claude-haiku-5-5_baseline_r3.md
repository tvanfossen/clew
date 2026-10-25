A tool call goes through several checks in `ToolExecutor`, and the deny list is only enforced at the very end, inside `ServerManager`. I traced it by reading the code; I did not build or run anything.

**Order of checks** (`src/mcp/tool_executor.cpp`)

```
process_single_call                                  :729
 ├─ PRE_TOOL_CALL hook (can cancel)                  :857
 └─ check_call_preconditions                         :667
     1. anti-spiral hard block                       :938
     2. schema validation (args vs input_schema)     :640
     3. MCP key-set auth (only if identity enforced) :575
     4. tier allowed_tools (gh#83)                   :198
     5. duplicate-call detection                     :117
     6. check_approval                               :161
 └─ execute_tool → ServerManager::execute           server_manager.cpp:153
     └─ permissions_.is_denied(...)  → "Error: Permission denied" result
     └─ route_tool_call → server / external client
```

**What `check_approval` decides** (`tool_executor.cpp:161`)

- `auto_ok = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(...)`. `auto_approve_tools` comes from `permissions.auto_approve` (`facade/entropic.cpp:1489`). The allow list is only consulted here.
- If not `auto_ok` and `on_tool_call` is set, the code sets `approved = true` anyway after invoking the callback. The callback returns `void`, so a frontend cannot veto through it. This reads as "notify and approve," not a prompt. I think that's a real gap; please confirm it's intended.
- If not `auto_ok` and there is no callback, the call is denied (headless mode).

**Where deny actually bites**

The deny list is not checked in `check_approval`. It runs in `ServerManager::execute` (`server_manager.cpp:157-165`), after approval has already happened. So a denied tool can still be auto-approved or shown to the user, and then fails at dispatch with a `Permission denied` result. A deny entry always wins over an allow entry, because allow only affects approval and deny blocks dispatch.

**What a pattern means** (`permission_manager.cpp:101`, `server_manager.cpp:426`)

- A pattern is split at the first `:`.
- The left side is an `fnmatch` glob against the tool name. With no colon, the pattern matches that tool with any arguments.
- The right side is an `fnmatch` glob against `tool:<argvalue>`. The flags are 0, so `*` also matches `/` and `;`. Nothing is parsed as a shell command.
- `argvalue` comes from `args_to_pattern`: it takes the first key in nlohmann's iteration order, which is alphabetical, not call order. If that value is a string, it is used. Otherwise, or with no args, it is `*`.

| Pattern | Matches |
|---|---|
| `bash.execute` | every `bash.execute` call, any args |
| `bash.*` | every tool on the bash server |
| `filesystem.read_file:/home/*` | reads whose first (alphabetical) string arg starts with `/home/` |
| `bash.execute:git *` | any command starting with `git ` (including `git status; rm -rf x`) |

Two consequences:

1. A deny like `bash.execute:rm *` can be bypassed if `command` is not the alphabetically first string argument. The match then runs against another argument's value.
2. `BashServer::get_permission_pattern` (`bash.cpp:200`) builds `execute:<base> *`, but nothing in `src/` calls it on the decision path. Only tests reach it. The real matching uses `args_to_pattern`, so the bash-specific pattern is dead for matching.

**Earlier gates**

Schema, MCP key-set, tier, and duplicate checks all run before approval. A rejection at any of them means approval and dispatch never happen.