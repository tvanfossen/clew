A clew index can be stale on three separate axes, and the tool tells the caller and, for queries, refreshes the index itself. I answered from the index only, so the details below come from docstrings and symbol bodies, not from running anything.

**How it knows**

`db_status` in `clew/mcp_server/state.py:1140` measures freshness for one target. It sets `stale` true when any of these holds:

- **Schema:** the database's build stamp differs from the server's `CLEW_BUILD_VERSION`. A stamp newer than the server expects is flagged as unclearable, since a rebuild would re-stamp the same newer version.
- **Data (source drift):** `_source_drift` finds source files changed since the build. The docstring notes that a version check alone missed edits, and mtimes are what catch them.
- **Code:** a server process older than its source is refused from building. `test_build_or_refresh_refuses_when_the_process_predates_its_source` cites a case where an old process rebuilt a newer index at the old version and dropped a layer.

`status` also reports coverage, refresh cost, and `stated_options`. The `staleness` block is present only when something is wrong, so it stays a signal rather than a permanent banner.

**What it tells the caller**

`staleness_notices` (`clew/mcp_server/server.py:1548`) stamps a list of `{axis, message}` entries onto every query reply. It never raises, so a failed measurement just means no annotation. The tool also changes its own claims. `_withdraw_definitive` (`clew/mcp_server/tools_query.py:257`) strips "this is a definitive empty result" from a reply when the schema axis is stale, because a missing layer makes an empty result unearned. On the data axis it does the same for a subject miss, since the symbol may postdate the build.

**What the caller does**

Two paths:

1. **Queries refresh first.** `_answering_with_refresh` (`server.py:519`) wraps each sync query tool. It calls `_auto_refresh` (`server.py:1242`) before answering, which rebuilds a data-stale index or starts building an absent one. `_refresh_stale` (`server.py:1294`) takes the per-repo build lock with a bounded wait. It re-checks staleness inside the lock, so concurrent sessions produce one build. If the build fails or the lock wait times out, the query answers from the existing index with its staleness notice attached. The caller gets a stale answer plus a warning rather than an error.
2. **Explicit refresh.** The `index` tool's `refresh` action rebuilds on request. Per the README, the refresh is incremental.

For the caller, the practical rule is: read `staleness` on every reply. If it names the schema axis, don't treat an empty result as definitive. If it names data drift on a miss, a refresh is needed, though normally the query has already tried one. If the code axis or a schema mismatch is reported, a rebuild won't clear it. A client restart, or a newer server, is the remedy.

I did not open `clew/mcp_server/freshness.py` directly. Its module brief describes the three axes, and I took the third axis's exact name from the test docs.