A clew index can be stale in three distinct ways, and the tool reports each one separately with the action that clears it.

**How it knows**

- **Data axis (index older than source):** `db_status` in `clew/mcp_server/state.py` sets `stale` when the index's build stamp differs from `CLEW_BUILD_VERSION` (currently 8), or when `_source_drift` finds source files changed since the build. It also reports `source_changed_files` and `newest_changed_source`. A version check alone cannot see source edits, so mtime drift is what catches them.
- **Schema axis (index newer than server):** `build_version` is above `expected_build_version`. A rebuild re-stamps the same newer version, so this cannot be cleared from this process.
- **Code axis (server process older than its source):** `code_identity` in `clew/mcp_server/freshness.py` compares the process fingerprint, taken at import, with the fingerprint of the source on disk. A stale process reads live data correctly but runs old logic when it writes.

**What it tells the caller**

- `freshness.notices()` returns a list of `{axis, message}` in the order data, schema, code. It is empty when the tool is current.
- Every query reply carries that list as a `staleness` block, but only when stale. `DocsDbServer.staleness_notices` in `clew/mcp_server/server.py` produces it and never raises. The block is sized to fit the response budget and compacted before it is dropped.
- The message for each axis names the remedy. Data is cleared by a rebuild. Code is cleared only by restarting the client. Schema cannot be cleared by any action the consumer can take.
- `index(action='status')` reports `stale` unconditionally, but it adds no interpretation block when the index is current.
- Staleness is reported per target. A routed reply is annotated only with the staleness of the repository it actually read, never the derived default.

**What the caller does**

- **Data stale:** call `index(action='refresh')`. Builds are serialised per target and the freshness check runs inside the lock, so concurrent refreshes produce one build. `duration_ms` reports the measured cost. `force=True` forces a rebuild even when the index looks current.
- **Code stale:** restart the MCP client, then refresh with `force=True`. `stale_code_refusal` makes `build_or_refresh` refuse before the build decision, so `force` cannot override it. The refusal message says so explicitly. A build through a stale process would drop whole pipeline layers and then report the index healthy.
- **Schema stale:** a rebuild does not help. The index was written by a newer clew, so the fix is to use a matching server.
- **Automatic refresh:** `_data_stale` triggers an automatic refresh only when the data axis is the sole problem and the process matches its source. Schema and code cases are never auto-refreshed.

One caveat: some of the bodies I pulled (`_staleness`, `build_or_refresh`) were flagged `anchor_mismatch`, meaning the file changed after indexing. I quoted their documented behaviour, not verified line numbers. The behaviour matches the tests named in the index (`test_freshness.py`, `test_mcp_server.py`).