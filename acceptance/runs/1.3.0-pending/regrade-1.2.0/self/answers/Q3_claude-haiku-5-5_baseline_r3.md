A clew index can be stale on three independent axes, and the tool reports each one with a different remedy. The caller is an MCP client (an agent), and the tool does most of the correction itself.

**How it knows**

- **Data axis (source drift):** `_source_drift` in `clew/mcp_server/state.py:823` stats every indexed source file (`path WHERE type=1`) and counts those whose mtime is newer than `clew.db`. Files more than 300 s in the future are ignored as edits, so a skewed clock cannot keep the index stale forever.
- **Schema axis (pipeline version):** `build_meta.build_version` is compared with `CLEW_BUILD_VERSION` (currently 8, in `clew/signature.py:203`). An index stamped with a newer version than the server means the server predates the index.
- **Code axis (process vs. source):** `code_identity()` in `clew/mcp_server/freshness.py` compares the fingerprint of the package source taken at process launch with the fingerprint on disk now. A mismatch means the running logic may be old.

`db_status()` (`state.py:1140`) combines these into `stale = not exists or build_version != current or source_changed_files > 0`. The axes are listed separately, so `stale` alone does not say which fix applies.

**What it tells the caller**

- `db_status` / `status` returns the raw fields (`source_changed_files`, `newest_changed_source`, `build_version`, `expected_build_version`, `code`, `refresh` cost) plus a `staleness` list present only when something is wrong.
- `freshness.notices()` turns those fields into `{axis, message}` entries. A current index gets none. The data notice names the count, the newest changed file and the cost of a refresh. The schema notice gives opposite advice depending on direction. When the index is older it says to run `index(action='refresh', force=True)`. When the index is newer it says rebuilding cannot clear the flag and the client must restart. The code notice says a rebuild cannot fix it and the client must restart.
- Every query reply carries the same `staleness` list through `answering()` (`server.py:1708`). `tools_query._withdraw_definitive` (`tools_query.py:~257`) also removes "definitive, do not retry" wording from an empty result when the schema or data axis is stale, because a missing row may just mean the index is older than the code.

**What the caller does**

1. **Data stale, code current:** the server handles it itself. `_auto_refresh` (`server.py:1242`) runs before a query, using `_data_stale` (`server.py:1204`), which returns false unless the process matches its source. `_refresh_stale` takes the per-repo build lock with a bounded wait, re-checks inside the lock so concurrent queries produce one build, and runs `_run_build` with `skip_if_fresh=True`. A failed refresh falls back to answering from the existing index, with the notice still attached. A background `keep_current` loop (`server.py:1538`, every `refresh_interval`) refreshes the session's touched indexes between queries.
2. **Explicit refresh:** `index(action='refresh')` calls `build_or_refresh` (`server.py:2189`). It skips with `built: false` when the index is already current, unless `force`, `exclude` or `options` is given. The reply reports `duration_ms` and the pipeline's own timings.
3. **Schema older than server:** the caller should rebuild with `force=True`.
4. **Schema newer, or code stale:** the caller must restart the MCP client. `stale_code_refusal` (`freshness.py:531`) refuses every write from a process that predates its source, and `force` cannot override it. `_first_build_refusal` also blocks automatic first builds in that state.

The CLI has its own refresh and status path, which I did not trace in full. The MCP path above is the one I verified in code.