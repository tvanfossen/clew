The index knows it is stale by comparing three independent facts, reports each one as its own "axis" with a remedy, and the query path refreshes on its own in the common case. Nothing in the query path makes the caller act on a notice unless it is a rebuild the server cannot perform.

**How it knows.** `db_status` in `clew/mcp_server/state.py` (`db_status`, ~L1140) computes `stale = not exists OR build_version != CLEW_BUILD_VERSION OR source_changed_files > 0`. The three inputs are:

- **Data:** `_source_drift` compares the indexed sources against the working tree, giving `source_changed_files` and `newest_changed_source`.
- **Schema:** the build version stamped in the database versus the pipeline version in this process.
- **Code:** `code_identity()` in `freshness.py` compares the process's import-time `PROCESS_SOURCE_FINGERPRINT` against the source fingerprint on disk. This catches the server running old logic after a fix, a case the index cannot see by looking at its own data.

**What it tells the caller.** `notices()` (`freshness.py:575`) turns those into a list of `{axis, message}`, ordered data, schema, code. Each message says what to do:

| Axis | Trigger | Message's advice | Clears it? |
|---|---|---|---|
| `data` | sources changed | `index(action='refresh')`, with the measured cost from the last build | yes, a rebuild |
| `schema` | index built by a newer pipeline than this process | rebuild, *unless* the index is newer than the server | only if the index is older than the server |
| `code` | process predates the source tree | restart the MCP client; rebuilding will not help | no, a restart |

The schema notice's direction matters. If the index is newer than the server, a rebuild re-stamps the same newer version and never clears the flag. The code notice says the query data is current even though the logic is old.

The annotation is attached to replies by `_staleness` / `answering` in `server.py` and `tools_query.py`, so each query reply carries `staleness` only when there is something to report. `status` also reports `stale` and the interpretation fields. A current index gets no notice at all.

**What the caller does.** The tool does most of the work itself:

- `_auto_refresh` (`server.py:1242`) runs before a query. If `_data_stale` is true it calls `_refresh_stale`, which takes a bounded per-repository build lock and re-checks inside it, so concurrent queries produce one build. If the index does not exist, it starts a background build.
- `_data_stale` returns false if the process predates its source, so an auto-refresh never writes an index with old logic.
- If the refresh fails or the lock wait times out, the query answers from the existing index and the `staleness` notice stays attached. The design goal is that a stale answer with a warning beats an error.
- `build_or_refresh` (`server.py:2199`) is the explicit path. It skips when the index is already current (unless `force=True`), and it returns a measured `duration_ms`. `stale_code_refusal` blocks writes from a stale process and ignores `force`. The remedy is a client restart, then `index(action='refresh', force=True)`.

A caller that ignores the notices still gets correct data for the data axis, because the query refreshes first. For the schema and code axes, the caller must act: restart the client, or rebuild only when the schema direction is "server older than index" is not the case.

**Current state here.** `index(action='status')` on this repository reports `stale: false`, `source_changed_files: 0`, build version 9 matching expected 9, and `matches_source: true`, so no notices are attached right now. One oddity I did not resolve: dossier flags `anchor_mismatch: true` on several symbols (`notices`, `check_version_staleness`, `build_or_refresh`, `_staleness`), meaning their recorded line ranges no longer match the source even though the index reports no drift. I did not verify whether that is a line-range bookkeeping issue or something else.