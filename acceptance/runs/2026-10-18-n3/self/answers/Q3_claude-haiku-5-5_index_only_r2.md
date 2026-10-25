The index knows it is out of date by comparing its own stamps against the running code and the source tree. It reports that on every reply, and the query path refreshes it automatically when it can. The caller only has to act when the reply says a fix is needed and no automatic one applies.

**How it knows (three axes)**

| Axis | Stale when | Cleared by |
|---|---|---|
| `data` | The source has drifted since the index was built, or the pipeline stamp is older | A rebuild (refresh) |
| `schema` | The index was stamped by a newer build than this process expects | Nothing this process can do; the server needs updating |
| `code` | The running server process loaded clew code that no longer matches the source tree | Restarting the MCP client, then a forced refresh |

`db_status` in `clew/mcp_server/state.py` computes these, and `notices()` in `clew/mcp_server/freshness.py` turns them into `{axis, message}` entries, ordered data → schema → code. `code_identity()` only reports `matches_source: false` on positive evidence, meaning two non-empty fingerprints that differ. An unreadable tree counts as a match, so the tool doesn't tell you to restart for no reason.

**What it tells the caller**

- Every query reply carries a `staleness` block, and only when something is stale. A current index adds nothing, so the warning stays meaningful. `staleness_notices()` in `clew/mcp_server/server.py` supplies it.
- The block is sized to the reply. `_staleness_within_budget` in `clew/mcp_server/tools_query.py` uses full prose when it fits, then a compact form, then a minimal one. A large answer keeps its warning, shortened.
- `status` reports `stale` plus the interpreted remedy. Its `staleness` field appears only when there is something to act on.
- The notice for a stale index says to call `status` for the diagnosis, and the code-axis refusal names the restart step.

**What the tool does itself**

- Before answering, `_answering_with_refresh` (`server.py:519`) wraps each query tool and calls `_auto_refresh`. If the data axis is stale and the process matches its source, it rebuilds the index and then answers. The refresh is deduplicated under a per-repository build lock with a bounded wait, so a stalled build can't hang the session. If the refresh fails, the query still answers from the old index, and the staleness notice goes with it.
- `_data_stale` refuses to refresh when the schema or code axis is the problem. Rebuilding through a stale process could re-stamp the index with old pipeline logic and silently drop layers.
- A background pass, `refresh_touched`, keeps the indexes this session has used current between queries.

**What the caller does**

1. Read the `staleness` block on the reply. Each entry names an axis.
2. For `data`, do nothing. The query path already rebuilds when it can. If the notice persists, call `index(action='refresh')`.
3. For `schema`, a rebuild won't help. The index is newer than the server, so update clew.
4. For `code`, restart the MCP client so it loads the current code, then run `index(action='refresh', force=True)`. A write through a stale process is refused, and `force` does not override that refusal.
5. Call `status` only when the reply's notice says the full diagnosis is needed. Don't open a session with it.

**Caveat:** I answered from the index alone. `_staleness` and `code_identity` came back with `anchor_mismatch: true`, so the recorded line numbers may not match the current file. I did not call `status` to check this repository's own index, since the design says to wait for the first query reply to flag staleness.