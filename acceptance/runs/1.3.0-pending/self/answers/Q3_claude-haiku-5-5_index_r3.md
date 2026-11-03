The index's own freshness is measured on every query, and the server fixes the data-axis case itself. Only the schema and code cases are left to the caller, and those are not fixed by rebuilding.

**How it knows.** `db_status` in `clew/mcp_server/state.py` computes `stale` as true when the database is missing, when its stamped `build_version` differs from `CLEW_BUILD_VERSION`, or when `source_changed_files > 0` (the source tree has drifted since the build). Each of those three conditions is a separate axis in `clew/mcp_server/freshness.py`, built by `notices()` and ordered data → schema → code:

| Axis | Trigger | Meaning |
|---|---|---|
| `data` | indexed source files changed | Index is behind the code. A refresh fixes it. |
| `schema` | stamped version ≠ server's expected version | Direction matters. If the index is newer, the server is old and a rebuild cannot clear it. If the index is older, a forced rebuild fixes it. |
| `code` | the running process fingerprint ≠ the source fingerprint on disk | The server loaded old logic. Only a client restart clears it. |

**What it tells the caller.** `notices()` returns an empty list when the index is current, so a current index carries no staleness text at all. When it is not, each query reply gets a `staleness` block. `QueryTools._staleness` in `tools_query.py` attaches it, sized to the reply's remaining budget, and annotates only the repository the reply actually read. `status` always reports the raw `stale` flag, but the interpreted `staleness` field appears only when there is something to act on. Measurement failures degrade silently and never turn a good answer into an error.

**What the caller does.**
- **Queries are refreshed automatically.** `_answering_with_refresh` wraps every synchronous query tool. Before answering, `_auto_refresh` checks whether the data axis is stale. `_data_stale` first requires `matches_source`, so a stale server never builds. If the index is stale, `_refresh_stale` takes the build lock with a bounded wait and re-checks inside the lock, so concurrent sessions produce one build. If the lock wait times out, or the build fails, the query answers from the stale index with its notice attached. An absent index starts a background first build.
- **Schema and code are never auto-refreshed.** A build through an old process would re-stamp the index with old pipeline logic and could drop layers.
- **Write paths refuse.** `stale_code_refusal` returns a `REFUSED:` message on the code axis. It has no override, and `force` does not bypass it. The message tells the caller to restart the MCP client, then run `index(action='refresh', force=True)`.
- **Explicit refresh.** `index(action='refresh')` accepts `sub_index`, and a background pass (`refresh_touched`, interval from `REFRESH_INTERVAL_ENV`) refreshes indexes the session has used.

**Caveats.** I read this from dossier and search output and did not run the refresh path. The `notices` and `_staleness` dossier replies were flagged `anchor_mismatch: true`, so the file has changed since the index was built and the line numbers quoted above may be off. I did not check the index's own freshness, since the query replies were not stale in this session.