The tool detects staleness in three independent ways, reports them as a `staleness` list on every query reply, and fixes only one kind automatically. The caller's job is to act on the notice, not to trust the answer.

**How it knows**

`db_status` (`clew/mcp_server/state.py` ~L1171–1232) measures three axes:

- **data**: `_source_drift` (state.py:823) stats every indexed source path in the database against the database's own mtime. Any file newer than the database counts as changed. Files dated implausibly far in the future are excluded and logged, so a skewed clock cannot keep the index stale forever.
- **schema**: `build_version` stored in the database versus `CLEW_BUILD_VERSION` in the running code.
- **code**: `clew/mcp_server/freshness.py` fingerprints the running process at import (`PROCESS_SOURCE_FINGERPRINT`) and compares it with a fresh fingerprint of the package's `.py` files. The fingerprint hashes relative path and content, not mtime, because git checkouts and touches would otherwise trip it with no real edit. `matches_source` is false only when both fingerprints are non-empty and differ. This axis means the server process is running old logic, not that the index is old.

`stale` in the status payload is true when the database is missing, the schema differs, or any source file changed.

**What it tells the caller**

`freshness.notices()` (freshness.py:573) returns a list of `{axis, message}`, empty when current. Each message names the action that clears it:

| Axis | Message says | Clearing action |
|---|---|---|
| data | N source files changed; cost of refresh from this target's own history | `index(action='refresh')` |
| schema, index older | index predates server; may be missing layers | `index(action='refresh', force=True)` |
| schema, index newer | server predates index; rebuilding cannot clear the flag | restart the MCP client |
| code | server loaded old logic; reads are fine, writes are affected | restart the MCP client; rebuild cannot fix it |

The list rides on every query reply as `staleness` (tools_query.py:1841–1844). When data staleness is present, a "definitively absent" answer for a missing subject is also withdrawn (tools_query.py:194–209), since a newer working tree is the likeliest explanation. A `status` call shows the raw fields alongside the same notices.

**What the server does on its own**

- Before each query, `_auto_refresh` (server.py:1242) rebuilds a data-stale index under the per-repository build lock, with a bounded wait. Concurrent queries deduplicate: the waiters re-check inside the lock and find nothing to do.
- A background `keep_current` loop (server.py:1538) calls `refresh_touched` on the session's working set, so the next query usually finds nothing to do.
- An absent index gets a background first build, but only for a git work tree or a registered repository.
- The automatic path refuses to build when the code axis is stale (`_data_stale`, server.py:1209; `stale_code_refusal`, freshness.py:531). `force` does not override that refusal. Build failures degrade to answering from the stale index with its notice intact.

**What the caller does**

1. Read `staleness` on every reply; treat its absence as the signal that the tool is current.
2. On a data notice, call `index(action='refresh')`, though the server usually does this already.
3. On a schema notice, refresh with `force=True` if the index is older; restart the client if the server is older.
4. On a code notice, restart the MCP client. Reads are still current, but writes through the stale process are refused.
5. Do not read a "not found" as a real negative while a data notice is present.

I read the code and did not run the test suite. Two details are from comments rather than code I checked: the 15-second loop interval and the idea that a refresh is cheap enough to pay on the query path.