**Short answer:** clew detects staleness on three separate axes, attaches a notice to every query reply, and the notice tells the caller which action clears it. Queries also refresh the data axis automatically before answering when it is safe to do so.

**How it knows.** Each axis is measured by a different check, and they are defined in `clew/mcp_server/freshness.py`:

| Axis | Meaning | How it is measured | Cleared by |
|---|---|---|---|
| `data` | Indexed sources changed since the build | `db_status` reports `source_changed_files` (`_data_notice`) | `index(action='refresh')` |
| `schema` | Build version differs from the server's expected version (`_schema_notice`) | Compares `build_version` with the server's expected build version | Refresh with `force=True` if the index is older. If the index is *newer* than the server, a rebuild cannot clear it, so the caller must restart the MCP client. |
| `code` | The running process loaded clew before its source tree changed (`_code_notice`) | Compares the process fingerprint with the on-disk source fingerprint (`code_identity`) | Only restarting the MCP client. Rebuilding does not help. |

Data is read live because query tools open the database per call. What goes stale on the `code` axis is the process's logic and module-level constants, not the data.

**What the caller gets.**
- `staleness_notices` (`clew/mcp_server/server.py`) rides on every query reply as a list of `{axis, message}`. It is empty when the index is current, so a current index adds nothing to the payload.
- Each message names the action that clears it. The `code` message says a rebuild cannot fix it. The `schema` message gives the direction-specific advice.
- The reply is trimmed to fit the payload budget (`_staleness_within_budget`), with a compact or minimal message when space is tight. Notices are attached only for the repository that actually answered, so a derived target's staleness is never reported beside another repository's data.
- A "not found" answer on a drifted index carries `_UNEARNED_BY_DRIFT`: the answer is not definitive, the caller should refresh and ask again, and it should check the `code` axis if the refresh did not run.

**What the caller does.**
1. Read the notice and act on the axis it names.
2. For `data`, call `index(action='refresh')`. Queries already refresh a stale data axis before answering (`_auto_refresh` → `_refresh_stale`). A background loop (`keep_current` → `refresh_touched`) also refreshes indexes in the session's working set on an interval. The refresh is deduplicated under a per-target build lock with a bounded wait. If the wait times out or the build fails, the query answers from the existing index and the staleness notice still rides along.
3. For `schema` with an older index, refresh with `force=True`.
4. For `code`, or for a `schema` index newer than the server, restart the MCP client. Rebuilding does not clear either one.
5. If a symbol is missing on a drifted index, refresh and ask again before concluding it does not exist.

**Writes are guarded.** `stale_code_refusal` makes `build_or_refresh` refuse when the process predates its source, and `force=True` does not override that. The reason is recorded in the code: a stale process reads current data but writes with old pipeline logic, and one measured case dropped a build layer and then reported the index healthy. The refusal tells the caller to restart the client and then refresh with `force=True`.

**Limitation I could not check from the index:** the `db_status` body in `clew/mcp_server/state.py` and the `status` tool wiring. I relied on the documented behaviour in the `freshness.py` module docs and the function docs. Some dossier results were flagged `anchor_mismatch`, so I cite functions by name rather than by line number.