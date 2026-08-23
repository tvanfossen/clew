I have enough to trace the full path now.

## The decision chain

A tool call passes through two independent gates before it ever reaches a server implementation, and they are asymmetric — one is a hard veto, the other is what decides whether the user gets a prompt.

**1. `ToolExecutor::check_approval()`** (`src/mcp/tool_executor.cpp:161`) runs as part of the preconditions pipeline (via `check_dup_or_approval` → `check_approval_pc`), *before* dispatch:
- `auto_ok = loop_config_.auto_approve_tools || server_manager_.is_explicitly_allowed(name, args_json)`
- `is_explicitly_allowed` forwards straight to `PermissionManager::is_allowed()`, which walks the **allow list** and does the fnmatch pattern check.
- If not auto-approved and not allow-listed, and a `callbacks_.on_tool_call` is registered, the callback fires and the call is treated as approved unconditionally (`approved = true` — the callback result itself isn't actually gated on the callback's return value here, it fires-and-approves). If no callback is wired at all, the call is denied outright with a warning log.
- An `ON_PERMISSION_CHECK` hook fires afterward purely for observability — it doesn't affect the outcome.

**2. `ServerManager::execute()`** (`src/mcp/server_manager.cpp:153`) runs later, at actual dispatch time, and checks the **deny list** via `PermissionManager::is_denied()`. This is a second, independent check against `permissions_` — same `PermissionManager` instance, but only its `deny_list_` is consulted here. If a deny pattern matches, execution is short-circuited with a `"Permission denied"` error response, regardless of what `check_approval()` decided earlier.

So the actual authority is split: **the allow list gates whether the human/callback gets asked at all** (an allow match skips prompting entirely), while **the deny list is checked independently, later, at dispatch, and wins regardless of anything decided upstream** — it's the true final veto. There's also a third, unrelated gate, `check_tier_allowed` (gh#83, v2.5.2), which enforces a locked tier's `allowed_tools` restriction at dispatch — a call outside that tier's allowlist is rejected even if permissions allowed it.

## What a pattern in each list does

Both lists hold the same pattern syntax (`PermissionManager::pattern_matches`, `src/mcp/permission_manager.cpp:101`): `tool.name` or `tool.name:arg_pattern`, matched with POSIX `fnmatch` (glob semantics — `*`, `?`, `[...]`). The tool-name portion is matched first; if it fails, the whole pattern fails regardless of the arg portion. If there's no `:`, the tool-name match alone is sufficient.

- **A pattern in the allow list**: lets a matching call **skip the approval prompt entirely** — e.g. `bash.execute:python*` auto-approves any bash call whose args-pattern starts with `python`, `filesystem.*` auto-approves every filesystem tool. It has no effect on the deny check.
- **A pattern in the deny list**: **unconditionally blocks** a matching call at dispatch time, overriding whatever the allow list or approval callback decided. It's checked independently and later, so an allow-listed, auto-approved, or user-approved call can still be killed here.

Because deny is checked separately in `ServerManager::execute` rather than jointly with allow in `check_approval`, "deny takes precedence over allow" (as the header comment states) is true only in the sense that deny gets the last word at dispatch — it is not evaluated as "deny-wins-if-both-match" in a single combined check.
