**Short answer:** the tool compares the index against the source tree and the running server, reports each mismatch as a named "axis" with the action that clears it, and refreshes the index itself before most queries. The caller's job is mostly to read the notice and restart the client when the notice says a rebuild won't help. This is from reading the code only; I did not run a live index.

**How it knows (three axes, `clew/mcp_server/freshness.py`, `state.py`)**

| Axis | Check | Cleared by |
|---|---|---|
| `data` | `_source_drift` in `state.py:823` counts indexed files whose mtime is newer than the database's mtime. Files dated in the future are ignored, with a warning. | `index(action='refresh')` |
| `schema` | `build_version` in the database vs. `CLEW_BUILD_VERSION`. If the index is older, a forced rebuild clears it. If the index is newer, the server is the stale one. | Forced refresh, or restarting the client |
| `code` | `source_fingerprint()` hashes the relative path and bytes of every `.py` in the package (not mtime). It is compared with the fingerprint taken at process import. | Only restarting the MCP client |

`db_status` (`state.py:1140`) assembles these. `stale` is true when the database is missing, the build version differs, or any file has drifted. Every axis is also reported as a `staleness` list through `notices()`. That list is empty when the index is current.

**What the caller is told**

- Every tier-1 query reply gets a `staleness` key when any axis is live (`server.py:1841`). If `data` is present, definitive-negative claims such as "not found" are withdrawn (`_withdraw_definitive`, `tools_query.py:257`), because a stale index can't prove absence.
- The message text names the action. `data` says to call `index(action='refresh')` and gives the measured cost. An older `schema` says to refresh with `force=True`. A newer `schema` or a `code` mismatch says a rebuild cannot fix it and the MCP client must restart. The code says that reads are still live and current, but writes would run old logic and drop layers.

**What the caller (or server) does**

1. **Query time, automatically.** Before answering, `_auto_refresh` (`server.py:1242`) checks `_data_stale`. This runs only if the process matches its source. If the index is stale, it runs `_refresh_stale` under the per-repo build lock, with a bounded wait and a re-check inside the lock, so concurrent queries produce one build. If the build fails, the query answers from the old index and the notice still rides along.
2. **Background.** `keep_current` runs every 15 s by default (`CLEW_REFRESH_INTERVAL`, `0` disables) and refreshes only indexes this session has touched.
3. **Explicit refresh.** `build_or_refresh` (`server.py:2277`) calls `stale_code_refusal` before any build. If the process predates its source, it returns `REFUSED:` and writes nothing. `force=True` does not get past that refusal.
4. **Caller duties.** Don't treat a negative result as definitive while `data` is in `staleness`. For `code` or a newer `schema`, restart the MCP client. Calling refresh again won't help.

**Gaps worth knowing**

- The `data` check is mtime-based, so a `git checkout` or `touch` can mark the index stale even with identical content. That is a deliberate trade-off against forcing rebuilds on every ordinary git operation.
- The `code` check is content-based, so it avoids that false positive, but it only detects drift and cannot repair it.
- Automatic refresh is skipped whenever the process predates its source. In that state the agent must restart the client, and a stale answer carries its notice until then.