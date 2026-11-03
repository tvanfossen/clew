**Short answer:** clew measures staleness on every query and attaches it to the reply. It names three separate causes. The caller is told which fix applies to each. Only one of the three is cleared by a rebuild.

**How it knows**

Staleness has three axes, each measured by a different check:

- **Data (sources changed).** `_source_drift` in `clew/mcp_server/state.py` compares each indexed file's mtime against the database's mtime. A version stamp can't see edits, so mtimes are the only signal. Files dated in the future are ignored and logged, so a skewed clock can't keep an index permanently stale.
- **Schema (pipeline version).** `db_status` compares the build version stamped in the database with `CLEW_BUILD_VERSION`.
- **Code (this server process).** `code_identity` in `freshness.py` checks whether the running process's fingerprint still matches the source tree on disk. If the package changed after launch, the running logic is old.

`db_status` (`state.py:1140`) combines these into `stale`, which is true if the database is missing, the stamp differs, or any source changed. It also reports the detail: `source_changed_files`, `newest_changed_source`, `build_version` versus `expected_build_version`, `age_days`, and a `refresh` cost measured on this target. The `staleness` block is present only when there is something to report, so a current index carries no warning.

**What it tells the caller**

`notices()` in `freshness.py:575` turns those measurements into `{axis, message}` entries, ordered by how likely the caller is to act on them:

| Axis | Trigger | Message says | Remedy |
|---|---|---|---|
| `data` | sources changed since build | N files changed, most recent X, so answers may describe code that no longer exists | `index(action='refresh')`, with its measured cost |
| `schema` (index older) | stamp < expected | index predates server, may be missing layers | `index(action='refresh', force=True)` |
| `schema` (index newer) | stamp > expected | server predates index | Restart the MCP client. A rebuild cannot clear it. |
| `code` | process fingerprint ≠ disk | server logic may be old | Restart the MCP client. A rebuild cannot clear it. |

These notices are attached to every query reply. `_staleness_within_budget` in `tools_query.py:160` fits them to the space left in the payload, compacting the text before dropping it, so a large answer doesn't lose its warning.

**What the caller does**

- **Data axis:** refresh. `build_or_refresh` (`server.py:2199`) runs the pipeline under a per-target lock. The freshness check happens inside the lock, so concurrent refreshes produce one build. The result includes `duration_ms`, which is measured, not estimated.
- **Schema axis, index newer:** restart the client. Rebuilding re-stamps the same newer version and never clears the flag.
- **Code axis:** restart the client. Rebuilding is unsafe here, not just ineffective. A stale process running an old pipeline would re-stamp the index with dropped layers. `build_or_refresh` refuses before the lock when the process predates its source, and `force` cannot override that.
- **Automatic refresh:** `_data_stale` (`server.py:1209`) only triggers a refresh on the data axis, and only when the process matches its source. Its callers are `_auto_refresh` and `_refresh_stale`. I did not read those two bodies, so I can't say exactly when they run beyond the 15 s `keep_current` loop mentioned in a comment.

**Where it can fail:** staleness is measured per reply, and an unreadable database or failed measurement degrades to "no annotation" rather than an error. A query can therefore return with no warning when the check itself failed. The code is written to prefer that over turning a good answer into an error, but it is a real gap in what the caller can rely on.