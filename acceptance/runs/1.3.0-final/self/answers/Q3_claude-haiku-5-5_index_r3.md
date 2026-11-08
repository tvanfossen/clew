The tool measures three separate kinds of staleness, tells the caller about each one in the reply, and in the query path it repairs the data axis itself. The caller's job is mostly to read the notice and, for code or schema problems, to restart the client rather than rebuild.

**How it knows (three axes)**

- **Data:** the index was built from source that has since changed. `_data_notice` in `clew/mcp_server/freshness.py:381` fires when `db_status` reports `source_changed_files > 0`.
- **Schema:** the index was stamped by a different pipeline build version than this server expects. `_schema_notice` (`freshness.py:412`) compares the stamped `build_version` with `CLEW_BUILD_VERSION`.
- **Code:** the running server process loaded clew before the package source changed. `code_identity()` (`freshness.py:221`) compares a fingerprint taken at import with the current source fingerprint. `matches_source` is False only when both fingerprints are non-empty and differ, so an unreadable tree does not produce a warning.

`notices()` (`freshness.py:575`) collects whichever axes apply, in the order data, schema, code, and returns an empty list when the index is current.

**What it tells the caller**

`DocsDbServer.staleness_notices()` (`server.py:1548`) is attached to every query reply as a `{axis, message}` list. The list is empty when nothing is stale, so a current index adds no noise. The message for each axis names the remedy:

- Data: "call `index(action='refresh')` to correct it", with the cost stated.
- Schema: when the index is newer than the server, the message says rebuilding cannot clear the flag and the client must restart. When the index is older, it says to call `index(action='refresh', force=True)`.
- Code: the message says a rebuild cannot fix it and the MCP client must restart.

`_withdraw_definitive` (`tools_query.py:257`) also rewrites an empty-result claim when the schema axis is stale, or when the data axis is stale and the subject was not found. A stale index is not allowed to say "definitively absent".

**What the server does on its own**

Before answering, `_auto_refresh` (`server.py:1242`) resolves the target. If the data axis is stale, it calls `_refresh_stale` (`server.py:1294`). That method takes the build lock with a bounded wait, re-checks staleness inside the lock so concurrent queries deduplicate into one build, and runs the build with `skip_if_fresh=True`. If the lock wait times out or the build fails, the query answers from the index as it stands, and the staleness notice still rides along. An absent index is built in the background instead.

`_data_stale` (`server.py:1209`) refuses to auto-refresh unless `matches_source` is true. The stated reason is that a server running older code would rebuild with that old pipeline logic and could drop layers while reporting health.

**What the caller does**

- **Data stale:** the query path already refreshed it. If the notice persists, call `index(action='refresh')`.
- **Schema stale, index older:** call `index(action='refresh', force=True)`.
- **Schema stale, index newer, or code stale:** restart the MCP client. A rebuild does not help in either case.
- **Writes:** `stale_code_refusal()` (`freshness.py:531`) makes write paths refuse while the code is stale. `force` does not override that refusal.

**A caveat from this session**

The dossier for `_staleness` and `notices` came back with `anchor_mismatch: true`, meaning the file changed since the index was built and those line ranges no longer match the function. The query replies carried no `staleness` block, so the index reported itself as current on the data axis. I did not check `db_status` directly, so I cannot say which of the two is right. Running `index(action='status')` would settle it.