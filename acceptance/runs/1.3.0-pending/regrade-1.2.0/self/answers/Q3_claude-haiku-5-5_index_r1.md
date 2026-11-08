**Short answer:** the index checks itself on every query, using three separate axes. Each axis reports a different remedy, and the tool refuses to rebuild in the cases where a rebuild would make things worse.

**How it knows** (`clew/mcp_server/state.py` `db_status`, `freshness.py`)

| Axis | Detected by | Cleared by |
|---|---|---|
| `data` | `_source_drift` stats each indexed file's mtime against the database's mtime. Files dated in the future are ignored and logged. | `index(action='refresh')` |
| `schema` | The stamped `build_version` differs from `CLEW_BUILD_VERSION`. | Rebuild if the index is older. If the index is newer, only restarting the client helps. |
| `code` | The running process's `PROCESS_SOURCE_FINGERPRINT` (taken at import) differs from the fingerprint of the source tree now. | Restarting the MCP client only. A rebuild runs the old logic. |

The stamp check alone was not enough. The `db_status` docstring records that a database built before any number of source edits still reported `stale: false`, so `data` was added as a second term.

**What it tells the caller**

- `db_status` returns the raw fields: `build_version`, `expected_build_version`, `source_changed_files`, `newest_changed_source`, `stale`, `age_days`, plus `refresh` cost and `coverage`. `stale` is true if the stamp differs, the sources have drifted, or the database is missing.
- `freshness.notices()` turns those into `{axis, message}` entries in the order data, schema, code. Each message names the action that clears it. It returns an empty list when the tool is current.
- Query replies carry a `staleness` block only when something is stale, so a current index adds no noise. The block is computed by `_staleness` for the repository the reply actually read, never the derived default.

**What the caller does**

1. **Reads the notice.** For `data`, the message says to call `index(action='refresh')` and includes the measured cost. For `schema` and `code`, the message says a rebuild cannot clear it. For `code` it also says that reads are still current but writes are not safe.
2. **Refresh path** (`build_or_refresh` → `_build_once`). The freshness check runs inside the per-target lock, so concurrent refreshes produce one build. Two gates come before the build:
   - `stale_code_refusal` refuses any write when the process predates its source. `force` does not override this, because the refusal sits ahead of the build decision.
   - The refusal reply tells the caller to restart the client, then run `index(action='refresh', force=True)`.
3. **Automatic refresh.** `_data_stale` only permits an auto-refresh when the `data` axis is stale and the process matches its source. It is non-raising, so a failed measurement degrades to "do not refresh" and never breaks a query.
4. **Acting on the answer.** The `schema` case where the index is newer than the server has no fix a consumer can take except restarting the client. The `code` case is the same. Only `data` is worth a refresh.

**What I did not settle**

- I did not confirm the `keep_current` background loop's cadence or whether anything starts it. The index shows no callers for `keep_current`, so its wiring is unverified.
- I did not run the tools against this repository. Everything above comes from the indexed docstrings and bodies, which were current in their `target` reply. I did not check the freshness of the repository's own index.