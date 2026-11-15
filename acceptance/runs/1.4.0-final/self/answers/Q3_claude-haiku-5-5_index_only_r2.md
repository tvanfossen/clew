A clew index knows it is out of date on three separate axes, computed on every reply. It tells the caller through a notice in the payload, and by default the server rebuilds the index itself before answering. Only the data axis is fixed by a rebuild.

**How it knows.** `db_status` (`clew/mcp_server/state.py`, `db_status`) compares the index with the world on three axes:

| Axis | Detected by | Meaning | Cleared by |
|---|---|---|---|
| `data` | `source_changed_files > 0` (indexed sources changed since the build) | The answer may describe code that no longer exists | `index(action='refresh')` |
| `schema` | stamped `build_version` ≠ `CLEW_BUILD_VERSION` | The index is from a different pipeline version | Refresh with `force=True` if the index is older. If the index is *newer* than the server, a rebuild cannot clear it. Restart the MCP client. |
| `code` | `code_identity()` says the running process's source fingerprint differs from the tree on disk | The server is running stale logic | Restart the MCP client. A rebuild is refused. |

Only `code` and `schema` are measured against the server's own build. `code_identity` reports `matches_source` as False only on positive evidence, meaning two non-empty fingerprints that differ. An unreadable tree is treated as current, so "cannot tell" does not produce a warning.

**What it tells the caller.** `notices()` (`freshness.py`) returns a list of `{axis, message}` in the order data, schema, code. The list is empty when the index is current, and a current index carries no `staleness` key at all. Each message names the remedy. The `data` message reads, roughly: "N indexed source file(s) have changed since this index was built… Call `index(action='refresh')` to correct it — [cost]." The cost clause comes from the index's own recorded refresh history, not a constant. The `code` and `schema` messages say explicitly that a rebuild will not help, so the caller does not loop. The notices ride in every query reply through `_staleness` (`tools_query.py`). If the reply is large, the notice is compacted, and then reduced to "stale — call status" as a last resort. Routed replies carry only the staleness of the repository they actually read.

**What the server does.** The caller is not expected to act on the notice, because the server acts first:

- `_auto_refresh` runs before each query. If `_data_stale` is true it calls `_refresh_stale`. If the index file is absent it starts a first build, subject to `_first_build_refusal`. That refusal stops a query from indexing a directory that is neither a git work tree nor a registered repository.
- `_data_stale` returns false if the process predates its source. This keeps an auto-refresh from running old pipeline logic and re-stamping the index with it.
- `_refresh_stale` takes the per-target build lock with a bounded wait, and re-checks freshness inside the lock. Concurrent queries therefore produce one build. If the lock wait times out or the build fails, the query answers from the existing index and the notice still rides along.
- `build_or_refresh` (manual `index(action='refresh')`) does the same freshness check inside the lock. `force=True` skips the freshness check but never the source-staleness refusal (`stale_code_refusal`), and it reports `duration_ms` for the call.

**What the caller does.**
1. Usually nothing. Automatic refresh handles `data`, and queries continue.
2. If a notice remains, or the auto-refresh failed, call `index(action='refresh')`. Use `force=True` only for a `schema` notice where the index is older.
3. For a `code` or a newer-`schema` notice, restart the MCP client. Do not trust a rebuild or treat the result as a fix. The `code` notice says a fix that is not visible in query results may just mean the server has not loaded it.
4. Call `index(action='status')` only when a notice needs the full diagnosis. The tool guidance says not to open a session with it.

**Caveats.** I answered from the index only. The `_staleness`, `build_or_refresh` and `db_status` dossiers were flagged `anchor_mismatch`, so their line numbers may not match the current source, and `db_status` and `build_or_refresh` bodies were truncated. The `_refresh_stale` and `_data_stale` bodies were complete. The `index` tool's own dispatch is `DocsDbServer.index`. It is not a symbol named `mcp__clew__index` in the source.