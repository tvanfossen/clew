A clew index can be out of date along three independent axes, and the tool tells the caller which one and what clears it. It also refuses to rebuild in the one case where a rebuild would make things worse.

**How it knows.** `db_status` in `clew/mcp_server/state.py` measures the database against the running code (version 12 of that function). Freshness is two-termed: the pipeline version that stamped the index differs from the one expected, or the source files have changed since the build. Version checks alone missed source edits, so mtimes are also compared. `db_status` also reports coverage, so an index can be current yet hold little of the repository.

**What it tells the caller.** `freshness.py` turns the raw fields into `notices()`, a list of `{axis, message}` entries in the order data → schema → code. Each message names the action that clears it. The three axes:

| Axis | Meaning | Cleared by |
|---|---|---|
| `data` | Sources changed since the build | Rebuild (`index(action='refresh')`) |
| `schema` | Index was stamped by a *newer* build than this server expects | Nothing the caller can do; a rebuild re-stamps the same newer version |
| `code` | The running server process loaded clew before its source changed | Restarting the MCP client only |

The notices ride inside the payload. `staleness_notices()` in `server.py` attaches them to every query reply, and a `staleness` block appears only when something is stale, so a current index adds nothing. The block is non-raising: if measuring fails, the reply goes out without it rather than turning into an error. When the index is schema-stale, `_withdraw_definitive` in `tools_query.py` also rewrites any "definitive empty result" note, so a reply cannot say both "no locks exist" and "layers may be missing."

**What the caller does.**

- **Queries refresh automatically.** `_answering_with_refresh` wraps each query tool and calls `_auto_refresh` before answering. `_data_stale` decides whether a refresh applies, and only the `data` axis qualifies.
- **Guards on the rebuild path.** `_data_stale` returns false when the process does not match its source, so an auto-refresh never runs the build that could corrupt the index. `stale_code_refusal()` is the guard every write path calls first. It has no override, and `force=True` does not bypass it.
- **Locking and failure.** `_refresh_stale` takes the per-repository build lock with a bounded wait. Concurrent queries deduplicate into one build, and a lock wait that times out answers from the existing index with its notice still attached. A failed refresh also degrades to answering with the warning, not an error.
- **Caller's manual step.** The caller's own move depends on the notice. For `data`, nothing is needed because queries already refresh. For `code`, the caller restarts the MCP client and then runs `index(action='refresh', force=True)`. For `schema`, the caller can't fix it from the client side.

**Why it's built this way.** The design records two earlier failures. Reporting staleness and leaving the fix to the caller meant agents answered from stale indexes anyway, so refresh is now automatic. A stale process once rebuilt an index at an older version and dropped a layer while `status` reported it healthy, so writes from stale code are refused.

Some of the line anchors I got back were flagged as mismatched against the current file, so treat the exact line numbers as approximate. The behaviour described above is consistent across the docstrings and tests.