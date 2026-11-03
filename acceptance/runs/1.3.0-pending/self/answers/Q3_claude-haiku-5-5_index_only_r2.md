**Short answer:** clew measures staleness on three separate axes. Query tools refresh a stale data index themselves before answering. The caller only has to act on the axes the tool cannot clear, and each of those needs a different action.

**How it knows.** `db_status` (`clew/mcp_server/state.py`) treats an index as stale when its build stamp is older than the server's, or when its sources have drifted since the build. Mtimes are what catch source drift: a version check alone once reported a pre-edit index as current. `freshness.py` names three axes:

| Axis | Meaning | Cleared by |
|---|---|---|
| `data` | Database is older than the source | Rebuild. Done automatically on query. |
| `code` | The server process loaded its modules before the source changed | Restarting the client only. Writes are refused until then. |
| `schema` | Index was stamped by a newer build than this server expects | Nothing the consumer can do. A rebuild re-stamps the same newer version. |

**What the caller is told.** Query replies carry a `staleness` block only when something is stale. A current index adds no notice, so the block stays a signal. Each notice says which action clears it. The `status` tool reports `stale` and interprets it. Replies that would make a definitive "no rows" claim against a schema-stale index have that claim rewritten, so a caller does not conclude a lock is absent when the real cause is an unrebuilt index.

**What the caller does.**
1. **Queries need no action for `data`.** `_answering_with_refresh` wraps each sync query tool. Before answering, `_auto_refresh` rebuilds a data-stale index under a per-repo build lock, and it builds an absent index in the background. Concurrent queries share one build. A refresh that stalls past `_LOCK_WAIT_SECONDS` (120 s) or fails degrades to answering from the old index, with the notice attached.
2. **`code` staleness:** restart the MCP client. `stale_code_refusal` makes any write path (`build_or_refresh`) refuse rather than build with old logic. `force` does not override it.
3. **`schema` staleness:** the index is newer than the server, so the fix is to run a matching clew build. Rebuilding through the same server does not clear it.
4. **Explicit refresh:** `index(action='refresh')` or `build_or_refresh` if you need the rebuild now rather than on the next query.
5. **Before concluding something is absent:** check the reply's `target` and any staleness notice first. A miss on a stale index is not evidence the symbol doesn't exist.

The design rejected two alternatives: reporting staleness and leaving the fix to the agent (agents often ignored the notice), and warning loudly while still writing (the warning was already present when a build dropped a layer). The notes cite these as measured incidents, not hypotheticals.

**Caveat.** This answer comes from the index's documentation and symbol bodies, not from running the tool. A few symbol lookups came back with line-anchor mismatches, so the exact line numbers may have drifted.