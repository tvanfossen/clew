Clew decides staleness itself, from three separate checks. It reports them as an annotation on every query reply, and the caller's remedy depends on which axis fired.

**How it knows (three axes, measured in `db_status`, `clew/mcp_server/state.py:1140`)**

| Axis | Measured by | Meaning | Cleared by |
|---|---|---|---|
| `data` | `_source_drift` (`state.py:823`) stats every indexed file's mtime against the database's mtime and counts newer ones (`source_changed_files`) | Sources changed since the build | A rebuild |
| `schema` | Compares `build_version` with the server's `CLEW_BUILD_VERSION` | The index was stamped by a different pipeline version | A rebuild if the index is older. If the index is newer, nothing clears it, because a rebuild re-stamps the same newer version. |
| `code` | `code_identity()` compares the process's import-time `PROCESS_SOURCE_FINGERPRINT` with a fingerprint of the source on disk | The running server loaded old code | Only restarting the MCP client |

`db_status.stale` is true when any axis fires. Future-dated mtimes are excluded from `data` drift, so a skewed clock cannot keep the index permanently stale.

**What it tells the caller**

- `freshness.py` turns each firing axis into a notice with `axis` and `message` (`notices()` at line 575, built by `_data_notice`, `_schema_notice` and `_code_notice`). The data notice gives the changed count, the most recently changed file, and the measured refresh cost. The code notice says a rebuild cannot fix it.
- `staleness` is attached to replies only when a notice exists (`DocsDbServer.staleness_notices`, `server.py:1548`, and `QueryTools._staleness`, `tools_query.py:1886`). A current index adds nothing, so the field stays a signal. The attachment is size-budgeted and never raises.
- `status` and `index` also report the raw fields (`stale`, `build_version`, `source_changed_files`, `code.matches_source`).

**What the caller does**

- **`data`:** call `index(action='refresh')`. Freshness is checked inside the per-target lock, so concurrent refreshes produce one build.
- **`schema` with an older index, or any `schema` mismatch the other way:** call `index(action='refresh', force=True)` to rebuild. If the index is newer than the server, restart the client instead.
- **`code`:** restart the MCP client. Refreshing is refused, as is a write.
- **Writes are guarded.** `build_or_refresh` (`server.py:2199`) calls `stale_code_refusal` before taking the lock. A stale process returns `REFUSED` and writes nothing, and `force` does not bypass it. The reason is a past incident where a stale process rebuilt a newer index at its own older version and dropped the `external` layer while reporting healthy.
- **Automatic refresh:** `_data_stale` (`server.py:1209`) triggers an automatic refresh only for the `data` axis, and only when the process matches its source. The docstring of `_source_drift` mentions a 15-second `keep_current` loop; I did not open that loop's body to confirm the details.

**Current state of this repo:** `index(action='status')` reports `stale: false`, `build_version` 9 matching expected 9, `source_changed_files: 0`, and `code.matches_source: true`. So no notice applies right now. A few function bodies (`_staleness`, `_staleness_within_budget`, `notices`) reported `anchor_mismatch`, so their line numbers may be slightly off.