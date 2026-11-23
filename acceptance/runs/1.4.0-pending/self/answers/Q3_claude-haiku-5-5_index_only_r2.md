A clew index knows it is out of date along three separate axes. The tool measures each one, reports each one, and the caller's remedy depends on which axis is stale.

**How it knows**

- **Data axis (sources changed).** `db_status` in `clew/mcp_server/state.py` compares the indexed source files against the tree and counts `source_changed_files`. `stale` is true when that count is above zero, or when the pipeline stamp differs from `CLEW_BUILD_VERSION`.
- **Schema axis (version mismatch).** `_schema_notice` in `clew/mcp_server/freshness.py` compares `build_version` with `expected_build_version`. The direction matters. If the index is newer than the server, a rebuild cannot clear it.
- **Code axis (the running process predates its source).** `code_identity()` in `freshness.py` compares the fingerprint captured at process start with the fingerprint of the source on disk. `matches_source` is False only on positive evidence that two non-empty fingerprints differ. An unreadable tree counts as a match, so the tool does not raise false alarms.

**What it tells the caller**

- `notices(status, code)` returns a list of `{axis, message}` in the order data, schema, code. It is empty when the index is current, so a current index adds nothing to query replies.
- Each message names the remedy. The data message says to call `index(action='refresh')` and attaches the measured cost of the last refresh. The schema message says to call `index(action='refresh', force=True)` when the index predates the server, and says not to rebuild when the server predates the index. The code message says a rebuild cannot fix it and the MCP client must be restarted.
- Query replies carry these notices in a `staleness` field, sized to fit the payload. `status` reports `stale` unconditionally and includes the interpretation only when there is something to interpret.

**What the caller does**

- **Data axis:** the server does most of the work itself. `_answering_with_refresh` wraps each query tool and calls `_auto_refresh` before answering. That path calls `_data_stale`, then `_refresh_stale`, which takes a bounded build lock and rebuilds with `skip_if_fresh=True`, so concurrent callers collapse into one build. A failed refresh is logged and the query still answers with its staleness notice. The background pass `refresh_touched` also keeps the session's indexes current between queries. An explicit `index(action='refresh')` remains available.
- **Schema axis:** if the server is older, the caller uses `force=True`. If the server is newer, the caller restarts the client.
- **Code axis:** the caller restarts the MCP client. Rebuilding does not help, and `stale_code_refusal` guards this. A write from a process that predates its source is refused with "Nothing was written," and `force` does not override the refusal. The refusal exists because a stale process once rebuilt an index at an older version and dropped a layer.

**Caveat:** I answered from the index only. Several dossiers flagged `anchor_mismatch`, so some line numbers may have drifted since the index was built. The function names and behaviour are consistent across the results.