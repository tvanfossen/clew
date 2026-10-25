A clew index can go stale along three independent axes, and each one is detected, reported and cleared differently. The logic lives in `clew/mcp_server/freshness.py`, `clew/mcp_server/state.py` and `clew/mcp_server/server.py`.

**How it knows**

| Axis | Detected by | Cleared by |
|---|---|---|
| `data` | `_source_drift` in `state.py:823` stats each indexed source file and counts those newer than the database's mtime. `stale` is also set when `source_changed_files > 0`. | Rebuild or refresh. |
| `schema` | `build_version` stamped in the index versus `CLEW_BUILD_VERSION` in `clew/signature.py`. Bumped whenever build output changes shape. | Rebuild when the index is older. If the index is newer than the server, only restarting the client helps. |
| `code` | `source_fingerprint` (`freshness.py:112`) hashes the relative path and bytes of every `.py` in the package and compares that with the fingerprint taken at process start. | Restart the MCP client only. |

The `code` axis hashes content rather than mtime on purpose. A `git checkout` or `touch` that leaves bytes unchanged must not trip a hard gate.

**What it tells the caller**

- `db_status` returns the raw fields (`build_version`, `expected_build_version`, `source_changed_files`, `newest_changed_source`, `stale`, `refresh` cost, and a `code` block). If anything is off, it adds `staleness`, a list of `{axis, message}` built by `notices()` (`freshness.py:573`). A current index gets no `staleness` key at all.
- Every query reply carries the same notices, via `staleness_notices` (`server.py:1548`) and `answering` (`server.py:1708`).
- Each message names the action to take. The `data` notice says to call `index(action='refresh')` and gives the cost. The schema notice points at `refresh(force=True)` for an older index. The schema notice also says a rebuild cannot help when the index is newer. The `code` notice says a rebuild cannot help, and that reads are still current but writes are not.
- When the index is schema-stale, `_withdraw_definitive` (`tools_query.py:194-270`) strips "definitive / do not retry" from empty results. A data-stale subject miss gets a "refresh and ask again" note instead.

**What the caller does**

1. **Query path, `data` axis:** the server does it for you. `_auto_refresh` (`server.py:1242`) rebuilds the stale index before answering, deduplicated under the repo's build lock with a bounded wait. If the refresh is refused or fails, the query still answers from the old index and the notice rides along.
2. **Explicit `index(action='refresh')`:** the caller runs this when it sees a `data` notice, or when a subject miss comes back with a data-stale note, then re-asks.
3. **`schema` axis, index older than server:** the caller runs `index(action='refresh', force=True)`.
4. **`schema` axis, index newer than server, or `code` axis:** the caller restarts the MCP client. Rebuilding does not clear it. The write path refuses while the code is stale (`stale_code_refusal`, called at `server.py:1393` and `server.py:2278`), and `force` does not override that refusal.

**Observations**

- The `data` axis is mtime-based while the `code` axis is content-based. The comments in `freshness.py` explain why content is the right test for `code`. The same reasoning arguably applies to `data`, so a `git checkout` can make `data` report stale when nothing changed.
- `_source_drift` fails closed to "no drift" on an unreadable database. In that case the `schema` axis is the only remaining signal.

I only read the code and did not run anything. The hook note appended to one of my shell results suggested calling `dossier`; I ignored it, since that tool isn't part of this question.