A clew index can be out of date on three separate axes, and the tool checks all three on every query. It tells the caller in two ways, and it fixes the data axis itself before answering in most cases.

**How it knows** (`clew/mcp_server/state.py:db_status`, `clew/mcp_server/freshness.py`)

| Axis | Detected by | Meaning | Can a rebuild fix it? |
|---|---|---|---|
| `data` | `source_changed_files > 0` (`_source_drift` on the indexed files) | Sources changed since the build | Yes |
| `schema` | `build_version` (stamped in the db) ≠ `CLEW_BUILD_VERSION` | Index and server were built by different pipeline versions | Only if the index is older. If the index is newer, a rebuild re-stamps the same newer version and cannot clear it |
| `code` | `code_identity()`: the running process's source fingerprint vs. the fingerprint of the tree on disk | The server loaded old code at launch and the package source has moved since | No. Only restarting the MCP client clears it |

`db_status` sets `stale` to true if any axis trips. `freshness.notices()` turns each tripped axis into a `{axis, message}` pair. It returns an empty list when the index is current, so a current index adds nothing to a reply.

**What it tells the caller**

- Every query reply carries a `staleness` block when any axis is tripped. `_staleness_within_budget` sizes it to the room left in the payload: full prose first, then a compact form, then a minimal form. The block is never dropped silently.
- The `status` reply (`index(action='status')`) reports the same thing in full: `stale`, `source_changed_files`, `build_version` against `expected_build_version`, `code`, and `refresh` cost. The data notice quotes the measured refresh cost so the caller can decide with a number.
- The `code` and `schema` messages carry explicit remedies. The `schema` message says a rebuild cannot help when the server predates the index, and the `code` message says a rebuild cannot help at all. Both tell the caller to restart the client.

**What the caller does about it**

1. **Automatic refresh before answering.** `_answering_with_refresh` wraps each synchronous query tool. Before the query runs, `_auto_refresh` resolves the same database the query will read, including `sub_index`. If `_data_stale` is true, meaning the `data` axis is stale and `matches_source` is true, `_refresh_stale` rebuilds it. The rebuild runs under the per-repository build lock, with a bounded wait, and re-checks staleness inside the lock so concurrent sessions deduplicate to one build. A failed refresh is logged and the query answers from the existing index, with the staleness notice still attached. The query never errors because of a failed refresh.
2. **Background refresh.** `keep_current` runs on a timer and calls `refresh_touched`, which refreshes only the indexes this session has used. The aim is that the next query after an edit usually finds nothing to do.
3. **Explicit refresh.** The caller can call `index(action='refresh')`, or `force=True` for a schema mismatch in the older-index direction. It should not rebuild for `schema` when the server is the older side, or for `code`. Restarting the client is the fix for those.

The automatic path never rebuilds when `matches_source` is false, because an old process running the pipeline could drop layers and re-stamp the index with the damage. The `code` notice says so explicitly.

**Caveats from the index itself**

- I did not trace the `index` tool's refusal path (`stale_code_refusal`) or the `status` handler in full. The description above of how the tool refuses those cases comes from the dossiers, not from reading those bodies.
- Several dossiers (`_staleness`, `_staleness_within_budget`, `notices`) came back with `anchor_mismatch: true`, meaning their recorded line numbers no longer match the source. The index is itself slightly behind the code it describes. Its bodies are still the ones it has recorded.