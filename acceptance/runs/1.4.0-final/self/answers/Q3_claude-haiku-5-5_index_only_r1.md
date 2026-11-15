The index tells its caller about staleness in three ways, and the server handles most of it itself. For this repository the index is current, so nothing needs doing now.

**How it knows.** `db_status` (`clew/mcp_server/state.py`) compares three things: the build version stamped in the database against the version the running code expects, whether any source file has changed since the build (`source_changed_files`, `newest_changed_source`), and whether the running server process still matches the source on disk (`code_identity`, `matches_source`). `stale` is true if the stamp is old, the sources have drifted, or the database is missing. The flag alone doesn't say what to do, so `freshness.py` splits it into three named axes, each with its own remedy.

| Axis | Meaning | What clears it |
|---|---|---|
| `data` | Sources changed since build | `index(action='refresh')`; queries also do this automatically |
| `schema` | Index stamped by a newer build than this process expects | Nothing through this process. A rebuild re-stamps the same newer version, so it stays stale |
| `code` | The server process loaded older code than is now on disk | Restart the MCP client, then `index(action='refresh', force=True)` |

**What it tells the caller.** `staleness_notices()` (`server.py`) returns a list of `{axis, message}` and attaches it to query replies as a `staleness` block. The block is absent when the index is current. It is sized against the real payload and compacted rather than dropped when space is tight, so a large answer still carries the warning. Reply payloads include the notice only when there is something to say. Measurement never raises, so a broken check degrades to no annotation rather than an error.

**What the server does before answering.** `_auto_refresh` (`server.py`) runs before every query:
- If the index is data-stale, it rebuilds it through `_refresh_stale`. The build takes a per-repository lock, re-checks staleness inside the lock so concurrent queries deduplicate to one build, and waits on the lock only a bounded time.
- If the lock wait times out, or the build fails, the query answers from the existing index and the staleness notice stays attached.
- If the index is absent, it builds one in the background.
- It never rebuilds on a `schema` or `code` axis. `_data_stale` returns false if `matches_source` is false, because a build through an old process would re-stamp the index with old pipeline logic.

**What the caller should do.**
- For `data`: usually nothing; the query refreshes. If a notice persists, call `index(action='refresh')`.
- For `code`: write paths refuse. `stale_code_refusal` returns a message telling the caller to restart the client and refresh with `force=True`. `force` does not bypass the refusal, because it only skips the freshness check.
- For `schema`: no rebuild helps; the caller has to change which clew version is running.
- Treat an empty or missing result on a stale index with care. Tests named `test_a_data_stale_subject_miss_withdraws_the_definitive_claim` and `test_schema_stale_index_withdraws_the_definitive_claim` indicate that a miss on a stale index is not a definitive negative, so a symbol added since the build may simply be absent.

**This repository now.** `index(status)` reports build version 9 against expected 9, zero changed source files, `matches_source: true`, and `stale: false`. Some dossiers came back with `anchor_mismatch: true`, meaning those function line ranges moved since the build. Status reports no drift, so I can't reconcile the two from the index alone. A refresh would settle it if it matters.