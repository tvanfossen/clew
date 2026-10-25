**How the tool knows.** There are three separate staleness axes, each checked in `clew/mcp_server/freshness.py`:

- **data**: the sources changed since the index was built. `db_status` in `clew/mcp_server/state.py` (~line 1195) counts `source_changed_files` by comparing file state against the database.
- **schema**: the index's `build_version` differs from the server's `CLEW_BUILD_VERSION`. The direction matters.
- **code**: the running server process imported its modules at launch, and the package source on disk has changed since. `code_identity()` (freshness.py:221) compares a content hash taken at import (`PROCESS_SOURCE_FINGERPRINT`) with one taken now. It hashes bytes, not mtimes, so a `git checkout` that restores identical content does not trigger it.

The top-level `stale` boolean in `db_status` covers only data and schema. The code axis is reported separately under `code.matches_source`, which is the gap gh#29 was about.

**What the caller is told.** `notices()` (freshness.py:573) turns the axes into a list of `{axis, message}` entries. It returns an empty list when the tool is current, so the annotation is absent in the normal case. The entries come back in this order:

- **data**: "N indexed source file(s) have changed… call `index(action='refresh')`", with the measured cost of a refresh.
- **schema**: if the index is older than the server, the message says to call `index(action='refresh', force=True)`. If the index is newer, it says to restart the client, because a rebuild re-stamps the same newer version and cannot clear the flag.
- **code**: "the LOGIC may predate the working tree… a rebuild cannot fix this, restart the MCP client." It also states that reads are current and writes are unsafe.

The notice rides on every query reply through `staleness_notices()` and `_staleness()` in `tools_query.py` (~1841). The tool also withdraws definitive "does not exist" claims when the index is stale. Schema staleness always does this, and data staleness does it for a subject miss (`_withdraw_definitive`, tools_query.py:257).

**What the caller does, and what the tool does on its own.** The tool does most of the work itself:

- **Before answering a query**, `_auto_refresh` (server.py ~1242) rebuilds a data-stale index under a bounded build lock and re-checks inside the lock, so concurrent queries share one build. It also starts a first build for a missing index, subject to guards.
- **In the background**, `keep_current` (server.py ~1538) calls `refresh_touched()` every interval for indexes this session has used.
- **Writes are refused** when the code axis is stale. `stale_code_refusal()` (freshness.py:531) runs before any build, and `force` does not override it. A stale process reads live data correctly but would write old logic over a newer index.

So the caller's job depends on the axis:

| Axis | Caller action |
|---|---|
| data | Usually none; auto-refresh handles it. Call `index(action='refresh')` if it failed or was refused. |
| schema, index older | `index(action='refresh', force=True)` |
| schema, index newer | Restart the MCP client. |
| code | Restart the MCP client, then refresh with `force=True`. |

If a notice is present and the caller reads a "not found" as definitive anyway, the reply itself says to refresh and ask again.