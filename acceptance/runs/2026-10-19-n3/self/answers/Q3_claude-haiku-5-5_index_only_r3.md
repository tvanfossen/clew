A clew index can go stale on three separate axes, and the tool checks them on every query rather than only when asked.

**How it knows**

- **Data:** the database is older than the source. The repo's own test notes say a version check alone cannot see source edits, so drift is detected from file mtimes.
- **Schema:** the build version stamped in the database differs from the one the server expects.
- **Code:** the running server process is older than the working tree. This is the case where a rebuild would be unsafe.

The check runs through `staleness_notices` in `clew/mcp_server/server.py`, which feeds `StalenessProvider` and `_staleness` in `tools_query.py`. A failing measurement is tolerated: the reply still goes out.

**What the caller sees**

Every query reply names its `target`. A `staleness` block appears only when some axis is stale; a current index adds nothing. The block lists which axes are in play. A data-stale miss is also flagged, because an empty result may come from an old graph.

**What the caller does**

- **Data stale:** `index(action='refresh')` rebuilds or updates incrementally. Queries also auto-refresh a stale index before answering, waiting up to `_LOCK_WAIT_SECONDS` for a refresh already in progress. If that wait runs out, the reply answers stale.
- **Schema stale:** a refresh does not clear it when the index is newer than the server. The caller has to fix the version mismatch, not rebuild.
- **Code stale:** the process must be restarted. Reads still return current data, but a build through the old process is refused, so it cannot re-stamp the index with old pipeline logic and drop layers. The tests cover that refusal.
- **Diagnosis:** `index(action='status')` is the full diagnosis. The server guidance says not to call it at the start of a session, since the reply's `staleness` block already announces problems.

**Caveat**

I answered from the index alone. The exact refresh and wait behaviour comes from docstrings and test notes, not from reading the implementation. I did not open the functions' bodies.