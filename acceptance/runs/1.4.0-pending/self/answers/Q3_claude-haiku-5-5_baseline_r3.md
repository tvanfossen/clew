A clew index can be stale on three independent axes. Clew detects each one differently, reports it in the reply, and the right fix depends on the axis. I answered from reading the code and did not run anything.

**How it knows**

- **Data axis (sources changed since build).** `db_status` in `clew/mcp_server/state.py:1140` calls `_source_drift` (`state.py:823`). It compares each indexed file's mtime against the database's mtime. Files dated in the future are excluded, and deleted files are skipped. Stale also means `build_version != CLEW_BUILD_VERSION` or `changed > 0`.
- **Schema axis (version mismatch).** `build_version` is compared with `CLEW_BUILD_VERSION` (`clew/signature.py`). The direction matters. If the index is newer than the server, rebuilding cannot clear it.
- **Code axis (the running process predates its source).** `code_identity()` in `freshness.py` hashes the relative path and content of every `.py` under the package, at import and again on demand. It compares the two digests. The check uses content, not mtime, so a `git checkout` that restores identical bytes does not trip it. An unreadable tree yields `""`, and that is treated as "cannot tell", not as a match.

**What it tells the caller**

- `freshness.notices()` (`freshness.py:573`) turns these into `{axis, message}` pairs. The list is empty when the tool is current.
- `db_status` exposes the raw fields (`source_changed_files`, `newest_changed_source`, `build_version`, `expected_build_version`, `refresh.duration_ms`, `code.matches_source`) and a `staleness` list when there are notices.
- Query replies carry the same notices under `staleness` (`tools_query.py:1841`). If the payload is too large, the notices are compacted and then minimised rather than dropped (`_staleness_within_budget`, `tools_query.py:158`).
- On a subject miss (`found: false`), `data` and `schema` staleness withdraw the "definitive negative" claim (`tools_query.py:200–209`). A symbol that is simply newer than the index is not reported as absent.
- Each message names the action that clears it. The data message says to call `index(action='refresh')` and quotes the measured cost. The schema message says to refresh with `force=True` when the index predates the server. The code message says a rebuild cannot fix it and the client must restart.

**What the caller does**

| Axis | Clearing action |
|---|---|
| data | `index(action='refresh')`. Cheap and incremental. |
| schema (index older) | `index(action='refresh', force=True)` |
| schema (index newer) | Restart the MCP client. Rebuilding cannot clear it. |
| code | Restart the MCP client. Refresh is refused. |

The server also acts on its own for the data axis. `_auto_refresh` (`server.py:1242`) runs before each query. It rebuilds only when the data axis is stale and the process matches its source. The build runs under a per-repo lock with a bounded wait. A re-check inside the lock deduplicates concurrent refreshes. Failures are logged and the query still answers from the old index, with its staleness notice attached.

Writes are refused when the process predates its source. `stale_code_refusal` is called in `build_or_refresh` (`server.py:2278`) and in first-build gating (`server.py:1393`). `force=True` does not bypass it.

**Things I noticed**

- The data axis still uses mtime. A `touch` or a checkout can therefore trigger a refresh with no content change. The refresh is incremental and the cache is sha256-keyed, so the cost is small, but it is not a true content check.
- I did not read the CLI path, so this covers the MCP surface only. I also did not read the body of `_staleness` in `tools_query.py`, so the exact withdrawal logic is taken from its comments.