**Short answer:** clew measures staleness on three independent axes every time it answers a query, attaches any finding to the reply, and refreshes automatically only when a rebuild would actually fix it. The caller's job is to read the notice and act on the axis it names. I traced this through the index; the call graph is confirmed, but I did not run anything.

**How it knows.** `DocsDbServer.staleness_notices` (`clew/mcp_server/server.py:1548`) calls `db_status(...)` for the database and `notices(status)` in `clew/mcp_server/freshness.py:575`. `notices` combines three checks, each returning a notice or `None`:

| Axis | Check | Meaning |
|---|---|---|
| `data` | `_data_notice`: `source_changed_files > 0` in `db_status` | Indexed sources changed since the build. A refresh fixes it. |
| `schema` | `_schema_notice`: `build_version` vs `CLEW_BUILD_VERSION` | The index and server disagree. The direction matters (see below). |
| `code` | `_code_notice`: `code_identity()` `matches_source` | The running process loaded clew before the source tree changed. |

`code_identity()` (`freshness.py:221`) reports `matches_source` as False only on positive evidence: two non-empty fingerprints that differ. An unreadable tree counts as current, so an unknown state never produces a warning.

**What it tells the caller.** Staleness rides in the payload. `QueryTools._staleness` (`tools_query.py:1886`) attaches the notices to query replies, sized to the remaining budget. A current index gets no block at all; the notice list is empty, and the tests assert this. For a routed reply, the notices come from the repository that was actually read, never the derived default. Each notice is a `{axis, message}` pair, and the message names the remedy. The data message says to call `index(action='refresh')`. The schema message is direction-dependent:
- **Index newer than server:** restart the MCP client. A rebuild re-stamps the same newer version, so `stale` cannot clear.
- **Index older than server:** `index(action='refresh', force=True)`.

The code message says a rebuild cannot fix it, and that only a client restart loads current code.

**What the caller does.** Two layers act before the caller does anything:
1. **Query time:** `_auto_refresh` (`server.py:1242`) runs before answering. If the data axis is stale, it calls `_refresh_stale` (`server.py:1294`), which takes the per-repository build lock with a bounded wait, re-checks staleness inside the lock to deduplicate concurrent refreshes, and falls back to answering with the notice intact on any failure. It also builds an absent index in the background.
2. **Background:** `keep_current` (`server.py:1538`) loops every interval and calls `refresh_touched`, which refreshes this session's indexes off the event loop.

`_data_stale` (`server.py:1209`) gates all of this. It refreshes only when the data axis is stale **and** `matches_source` is true. The schema and code axes are never auto-refreshed, because a build from a stale server process would re-stamp the index with old pipeline logic and could drop layers. The auto-refresh path never attempts that build.

For the caller (an agent or a human), the rule is: if a reply still carries a `data` notice, the refresh failed or was skipped, and the answer may describe code that no longer exists. Call `index(action='refresh')`. If it carries a `schema` or `code` notice, a rebuild will not clear it; restart the client, or force-refresh only for the older-index schema case.

**Caveats.** Four dossiers (`staleness_notices`, `notices`, `_staleness`, `check_version_staleness`) reported `anchor_mismatch: true`, so the index was built against a slightly different version of those files. Their bodies and the claims above come from the index's recorded text, not a fresh read. I did not verify `db_status`'s measurement of `source_changed_files` itself.