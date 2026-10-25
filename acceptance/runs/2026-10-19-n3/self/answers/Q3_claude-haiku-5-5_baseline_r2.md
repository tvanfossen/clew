The tool detects staleness on three separate axes, reports each one with its own remedy, and refreshes the data axis itself before answering. The caller mostly just reads the reply and, for two of the three axes, has to act.

**How it knows.** `db_status` in `clew/mcp_server/state.py` computes three things:

| Axis | Check | Cleared by |
|---|---|---|
| `data` | `_source_drift` stats each indexed source file against the database's own mtime (`state.py:823`). Future-dated mtimes are ignored so a skewed clock can't force rebuilds forever. | Rebuild (`index(action='refresh')`) |
| `schema` | `build_version` stamped in `build_meta` vs `CLEW_BUILD_VERSION` in `clew/signature.py`. | Rebuild if the index is older. If the index is newer, only restarting the client helps. |
| `code` | `code_identity()` in `clew/mcp_server/freshness.py` hashes the relative paths and content of every `.py` under the package, and compares that to a fingerprint taken at process import. | Restarting the MCP client only. A rebuild cannot fix it. |

`stale` is the boolean OR of these, but the docstrings are explicit that the boolean alone doesn't say what to do. That is why the axes are separate.

**What it tells the caller.**
- `db_status` adds a `staleness` list of `{axis, message}` only when something is stale. Each message names the remedy. A current index gets no annotation at all.
- Every query reply is stamped with a `staleness` block through `_staleness` in `tools_query.py`. The block is sized to the remaining response budget and compacts to shorter text if needed, but the axis token always survives.
- When the schema or data axis fires on a subject miss (`found: false`), `_withdraw_definitive` in `tools_query.py` strips the "definitive negative, do not retry" wording. The reply then says a symbol may be missing because the index is stale, not that it doesn't exist.
- Stale replies also carry `target`, so the caller knows which repository answered.

**What the caller does.**
- **Data axis:** mostly nothing. Before answering, `_auto_refresh` in `clew/mcp_server/server.py` rebuilds the index (incremental, under a per-repo lock, with the lock re-checked so concurrent sessions don't duplicate the build). If the refresh is refused or fails, it answers from the stale index with the notice attached. The caller can also call `index(action='refresh')` explicitly.
- **Schema axis, index older than server:** `index(action='refresh', force=True)` to rebuild the whole thing. The notice says so.
- **Schema axis, index newer than server:** a rebuild cannot clear it, because the rebuild re-stamps the same newer version. The notice says to restart the client.
- **Code axis:** restart the client. Reads are still live and current, because each query opens the database fresh. Writes are the hazard. `stale_code_refusal` makes every build path refuse with `REFUSED:` and write nothing, since an old process would rebuild the index with old pipeline logic and silently drop layers.

**Caveats I noticed.**
- The `data` check is mtime-based, so `git checkout` or `touch` can mark an index stale even when the content is unchanged. The `code` axis deliberately uses content hashes, because an mtime there would disable auto-refresh after an ordinary git operation. The two axes use different methods on purpose.
- Cross-file call additions in Python and Rust don't always reach the incremental splice, so those wait for a full rebuild (per the README's "Refreshing an index" section).