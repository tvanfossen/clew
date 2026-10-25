**How it knows.** `db_status` (`clew/mcp_server/state.py:1140`) measures staleness on three axes. `notices()` (`clew/mcp_server/freshness.py:575`) turns each stale axis into a `{axis, message}` pair:

| Axis | Trigger | Remedy the notice gives |
|---|---|---|
| `data` | `source_changed_files > 0`, from `_source_drift` comparing indexed files against disk | `index(action='refresh')` |
| `schema` | stamped `build_version` ≠ the server's `CLEW_BUILD_VERSION` | Direction matters. Index newer than server: restart the MCP client, because a rebuild re-stamps the same newer version. Index older: `index(action='refresh', force=True)` |
| `code` | `code_identity().matches_source` is false, meaning the running process loaded older clew code than is on disk | Restart the MCP client. A rebuild cannot fix it. |

**What it tells the caller.** Every query reply carries a `staleness` list, but only when at least one axis is stale. A current index adds no key at all, so the field works as a signal. The list is ordered data → schema → code, and it is sized to the 64 KB response budget (`_staleness_within_budget`, `tools_query.py:160`), compacting rather than dropping when the payload is large. The notices are also stamped onto replies from a routed sub-index, so the warning matches the database that answered. Measurement never raises; a failure just omits the notice.

**What the caller does.** There are two layers.

1. **The server acts first on the data axis.** `_answering_with_refresh` (`server.py:519`) wraps each sync query tool. Before answering, `_auto_refresh` (`server.py:1242`) checks whether the data axis is stale and whether the process matches its source. `_data_stale` refuses when the process predates its source, so an automatic build cannot re-stamp the index with old pipeline logic. If the check passes, `_refresh_stale` (`server.py:1294`) rebuilds under the per-repo build lock. The wait is bounded, and it re-checks staleness inside the lock, so concurrent sessions produce one build. A failed build still answers from the existing index with its notice attached. A background pass, `refresh_touched` (`server.py:1506`), refreshes indexes the session has used between queries.

2. **The agent handles what the server won't.** The automatic refresh covers only `data`. For `schema` and `code`, the agent has to read the notice and act: restart the client, or force a rebuild in the one schema case where that helps. The `index(action='status')` call is the full diagnosis for when the agent wants more than the notice.

One observation from this session: several dossier replies came back with `anchor_mismatch: true` (for `_staleness`, `_staleness_within_budget`, `check_version_staleness`). That is a per-symbol signal that the file changed since the index was built. I did not see a `staleness` block on those replies, so I can't tell from here whether the automatic refresh had already run.