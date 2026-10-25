**Short answer:** the tool measures staleness on three separate axes, attaches a per-axis notice to every query reply, and then acts on the data axis itself. A caller only has to act on the code and schema axes, and those need a client restart or a forced rebuild rather than a plain refresh.

**How it knows (three axes)**

| Axis | Check | Where |
|---|---|---|
| `data` | Any indexed source file has an mtime newer than the database file (future-dated mtimes are ignored). Reports a count and the newest changed path. | `_source_drift`, `clew/mcp_server/state.py:823` |
| `schema` | Stored `build_version` differs from `CLEW_BUILD_VERSION`. | `db_status`, `clew/mcp_server/state.py` (~1180–1210) |
| `code` | A SHA-256 over the package's `.py` contents (relative paths, not mtimes) differs from the fingerprint taken when this server process imported. | `source_fingerprint` / `code_identity`, `clew/mcp_server/freshness.py` |

`db_status` returns all of this, plus a single `stale` boolean that is true if any axis fires. The boolean alone doesn't say what to do, which is why the per-axis fields exist.

**What it tells the caller**

`freshness.notices()` turns the measurements into `{axis, message}` entries, ordered data → schema → code. The list is empty when the index is current, so a current index adds nothing to the reply. The server attaches the list as a `staleness` block on query replies (`staleness_notices`, `clew/mcp_server/server.py:1548`). If the block won't fit the response budget, the messages are compacted and then reduced to a minimal form, but the axis token is always kept (`_staleness_within_budget`, `clew/mcp_server/tools_query.py:158`). Each message names its remedy:

- **data:** "N source file(s) have changed… call `index(action='refresh')`", with the measured cost of a past refresh.
- **schema:** if the index is newer than the server, a rebuild cannot clear it, so the message says to restart the client. If the index is older, it says to call `index(action='refresh', force=True)`.
- **code:** reads are still current because each query opens the database fresh, but writes are refused. A rebuild cannot fix it, so the message says to restart the MCP client.

**What the caller does**

Most of the work happens in the server, not the caller:

1. **On every query**, `_auto_refresh` (`server.py:1242`) checks whether the target is data-stale. It only refreshes if the process matches its source (`_data_stale`, `server.py:1212`). A stale index is rebuilt under the per-repo build lock with a bounded wait, and the lock is re-checked inside so concurrent queries share one build. If the index file is missing, a first build starts in the background.
2. **If the refresh fails**, the query still answers from the stale index, and the notice stays attached.
3. **A background loop** (`keep_current`, `refresh_touched`) refreshes indexes that have been touched.
4. **Explicit writes** go through `stale_code_refusal` (`freshness.py:531`) before any build. `force=True` does not get past it. The refusal is returned as `REFUSED:`, and the fix is to restart the client, then refresh.

The caller's remaining job is therefore narrow. Ignore a `data` notice, because the server will fix it on the next query. Restart the client on a `code` notice or a newer-index `schema` notice. Use `force=True` only on an older-index `schema` notice.

**Caveats**

- The `data` axis is an mtime comparison, so a `git checkout` that rewrites files will count as drift even when the content is unchanged. The `code` axis uses content hashes specifically to avoid that false positive.
- The `stale` boolean merges all three axes, so a consumer that only reads it can't tell which remedy applies.