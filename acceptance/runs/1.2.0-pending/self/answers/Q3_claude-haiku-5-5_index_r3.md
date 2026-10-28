**Short answer:** clew checks its own currency on every query and attaches the result to the reply. It measures three independent axes and gives a different remedy for each. The index itself also tries to fix the data axis automatically before answering. The caller's job is mostly to read the remedy and act only when the reply says to.

**How it knows.** `db_status` (`clew/mcp_server/state.py:1140`) computes the facts:
- **Data:** `source_changed_files` counts indexed sources that changed since the build. A missing database also counts as stale.
- **Schema:** `build_version` (stamped in the index) is compared with `CLEW_BUILD_VERSION` (this process's pipeline version).
- **Code:** `code_identity()` checks whether this server process still matches the source tree on disk. A running process can predate the working tree after a fix lands.

`stale` is true if any of these fire. The status dict is also the source for each axis's notice.

**What it tells the caller.** `notices()` (`clew/mcp_server/freshness.py:575`) returns a list of `{axis, message}` in the order data, schema, code. Each message carries its own remedy. The list is empty when the index is current, and the `staleness` key is absent from the payload in that case. Every query reply is stamped with `staleness_notices()` (`server.py:1548`), which is non-raising, so a failed measurement cannot turn a good answer into an error.

| Axis | Meaning | Remedy the message gives |
|---|---|---|
| `data` | Sources changed since build | `index(action='refresh')`, with the measured cost |
| `schema`, index older than server | Index predates server; may lack whole layers | `index(action='refresh', force=True)` |
| `schema`, index newer than server | Server predates index | Restart the MCP client. A rebuild cannot clear it, since it re-stamps the same newer version. |
| `code` | Process loaded old logic | Restart the MCP client. A rebuild cannot fix it. |

The code notice also says the data is still current. Queries open the database per call, so the stale part is the process's logic, not the stored rows.

**What the caller does.**
1. **Automatically, for the data axis.** Before answering, `_auto_refresh` (`server.py:1242`) calls `_data_stale`. If the process matches its source and the data axis is stale, it refreshes the index first, so the caller gets fresh data without asking. Concurrent callers share one build because the re-check happens inside the lock. If the refresh fails, the reply still answers from the old index and keeps its staleness notice.
2. **Explicitly, for the other axes.** The caller has to act on the notice, and the refusal logic keeps it from doing harm:
   - `build_or_refresh` (`server.py:2199`) refuses to build when the process predates its source. This check runs before `force` and cannot be overridden. `stale_code_refusal` (`freshness.py:531`) gives the wording.
   - `_data_stale` also declines an automatic refresh in that situation, so a stale server cannot rebuild the index with old pipeline logic.
   - For the schema-older-index case, the caller can pass `force=True` to rebuild.
3. **Otherwise, nothing.** A current index carries no notice, so an agent need not check `status` before using it.

**Caveats.** I verified this by reading the source through the index, not by running a stale index and inspecting a real reply. The design reasoning in the docstrings is the project's own account, and I did not test it against the tests.