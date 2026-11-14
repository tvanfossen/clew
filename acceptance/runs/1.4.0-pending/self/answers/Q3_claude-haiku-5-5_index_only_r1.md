A clew index can be stale on three independent axes, and the tool reports each one in every query reply. The caller's remedy depends on which axis fired. For this repository the index is current: `status` shows build version 9 matching the expected 9, zero changed source files, and a source fingerprint that matches the running code.

**How it knows**

`db_status` in `clew/mcp_server/state.py:1140` computes `stale` as true when any of these holds: the database is missing, its stamped build version differs from the expected one, or `source_changed_files > 0`. The last term compares source mtimes against the build, so edits made after a build are caught even when the pipeline version has not changed. `code_identity()` in `clew/mcp_server/freshness.py:221` covers the third axis: it compares the fingerprint of the running process with the fingerprint of the package source on disk. It reports `matches_source: false` only on positive evidence that two non-empty fingerprints differ, so an unreadable tree does not cause a false warning.

**The three axes**

| Axis | Meaning | Who can clear it |
|---|---|---|
| `data` | Indexed source files changed since the build | A rebuild (`index(action='refresh')`) |
| `schema` | The stamped build version differs from the server's | A forced rebuild if the index is older; a client restart if the index is newer, because a rebuild re-stamps the same newer version |
| `code` | The server process loaded clew before its source changed | Only a client restart; a rebuild cannot fix it |

`notices()` in `freshness.py:575` builds the list in the order data, schema, code. It returns an empty list when the tool is current.

**What the caller receives**

Each query reply carries a `staleness` block only when a notice exists, so a current index adds no key at all. `staleness_notices()` in `server.py:1548` gathers the notices, and `_staleness` in `tools_query.py:1886` attaches them under a size budget. The data notice includes the number of changed files, the most recently changed file and the measured cost of a refresh. The code notice explicitly says that a rebuild will not help. Both are designed not to let the reader conclude that the data is wrong when only the server is out of date.

Measurement is non-raising throughout. A failure to measure degrades to no annotation, so the staleness check cannot turn a good answer into an error.

**What the caller does about it**

- **Query path, automatic:** before answering, `_auto_refresh` (`server.py:1242`) calls `_data_stale`. That method refuses to refresh when the process source does not match, because a stale process would rebuild with old pipeline logic. If the data axis is stale, `_refresh_stale` (`server.py:1294`) takes the per-target build lock with a bounded wait and re-checks staleness inside the lock, so concurrent queries produce one build. A failed or timed-out refresh falls back to answering from the existing index, with the notice still attached.
- **Explicit refresh:** the caller calls `index(action='refresh')`. `build_or_refresh` (`server.py:2199`) skips the build when the index is already current, unless `force` is set. It refuses outright when the process predates its source, through `stale_code_refusal` (`freshness.py:531`), and `force` cannot override that refusal.
- **Schema or code axis:** the caller restarts the MCP client to load current code, or forces a rebuild for an index older than the server. It does not retry the rebuild in a loop.
- **Reading the reply:** the caller should check the `staleness` block and the `target` it names before trusting an answer. A `data` notice means an answer may describe code that no longer exists.