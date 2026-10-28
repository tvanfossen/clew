A clew index can go stale in three independent ways, and the tool checks each one, reports it, and in most cases repairs it before answering.

**How it knows**

The three axes are defined in `clew/mcp_server/freshness.py:62-64`: `data`, `code` and `schema`.

- **Data (sources changed).** `_source_drift` in `clew/mcp_server/state.py` (~line 826) opens the index read-only, takes every `path` row with `type=1`, and stats each file on disk. Any file with an mtime newer than the database's mtime counts as changed. Mtimes more than 300 s in the future are ignored and logged, because they would otherwise keep the index stale forever.
- **Schema (pipeline version).** The index stores `build_version`. `db_status` compares it with the server's `CLEW_BUILD_VERSION`.
- **Code (server process).** `code_identity()` compares the fingerprint taken when the process imported its modules with the fingerprint of the source tree on disk. This is the axis that catches a fix that is committed but not yet loaded by the running server.

`db_status` (state.py ~1171) combines the data and schema checks into `stale = not exists or build_version != CLEW_BUILD_VERSION or changed > 0`. It does not include the code axis, which is why `stale: false` can coexist with a stale process.

**What it tells the caller**

- `db_status` / `index(action='status')` returns `build_version`, `expected_build_version`, `source_changed_files`, `newest_changed_source`, `stale`, `age_days`, a measured `refresh` cost, and `code`.
- `notices()` (freshness.py:573) turns those fields into a `staleness` list of `{axis, message}`. The list is empty when the index is current, and it is attached to a query reply only when the index is stale. Each message names the action that clears it:
  - **Data:** call `index(action='refresh')`.
  - **Schema, index older than server:** call `index(action='refresh', force=True)`.
  - **Schema, index newer than server, or code stale:** restart the MCP client. A rebuild cannot clear these, because it re-stamps the same newer version or the running process still holds old logic.

**What the caller does**

The server does most of the work itself, so the caller usually does nothing.

1. **Before every query**, `_auto_refresh` (server.py ~1236) checks whether the data axis is stale. If it is, `_refresh_stale` rebuilds the index under the repo's build lock. The lock wait is bounded, and the freshness check is repeated inside the lock, so concurrent sessions produce one build. If the refresh fails or times out, the query still answers from the stale index and the reply carries the `staleness` notice.
2. **Between queries**, a `keep_current` loop runs every 15 s (`DEFAULT_REFRESH_INTERVAL_SECONDS`, server.py:721) and calls `refresh_touched`, so the next query usually finds nothing to do.
3. **An explicit refresh** goes through `build_or_refresh` → `_build_or_skip`. It skips the build when `db_status` says the index is current, unless `force`, `exclude` or `options` is given. A write is refused before any build if the process code is stale (`stale_code_refusal`, freshness.py:531). `force` does not override that refusal.
4. **The calling agent** is told not to open a session with a status call. It should read the `target` and `staleness` fields on each reply. If a `staleness` block appears, the agent can call `index(action='refresh')` or, for the code axis, restart the client.

**Caveats**

- The data check is mtime-based. A `touch` with no content change triggers a rebuild, and a clock skew of more than 5 minutes is silently discounted.
- I read this from source and did not run it, so the claims about timing (the 15 s loop and the lock wait) are as coded, not measured.