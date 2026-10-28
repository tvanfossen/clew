A clew index is judged stale on three independent axes. The tool reports them as a `staleness` block on every query reply, and it refreshes the data axis itself. The caller's job is mostly to read the block and, for the code and schema axes, restart the MCP client, since a rebuild cannot clear those.

**How it knows (`clew/mcp_server/state.py`, `db_status` at ~L1140)**

| Axis | Check | Cleared by |
|---|---|---|
| `data` | `_source_drift` (~L823) stats every indexed path and counts files whose mtime is newer than the db file. Mtimes more than 300 s in the future are ignored and logged. | Rebuild (`index(action='refresh')`) |
| `schema` | `build_version` stamped in the db vs. `CLEW_BUILD_VERSION` | Rebuild if the db is older. If the db is *newer* than the server, only a client restart helps. |
| `code` | `freshness.py`: SHA-256 over relative path and content of every `.py` in the package (~L112), compared with the fingerprint taken at import (~L178) | Client restart only. The running process holds old logic. |

`stale` is true when the db is missing, the version differs, or `changed > 0` (`state.py:1197`). `freshness.notices()` (`freshness.py:573`) turns the axes into `{axis, message}` pairs, and each message names the action that clears it. The `code` message also says reads are current but writes are not, because a stale process writing through old logic dropped whole layers in a past incident (gh#348).

**What the caller sees**

- Every query reply gets a `staleness` block when any axis fires, and it is absent when the index is current (`tools_query.py:1841`).
- When an axis is stale, a definitive "not found" claim is withdrawn (`_withdraw_definitive`, `tools_query.py:257`). An empty answer is not trusted as proof of absence.
- `index(action='status')` returns the full payload: both version integers, `changed` count, newest changed path, the cost of a refresh measured from the target's own history, and the `code` identity.

**What the tool does before the caller acts**

- Before each query, `_auto_refresh` (`server.py:1242`) rebuilds a data-stale index under the per-repo build lock, with a bounded wait. It only does this when the process `matches_source`. It never raises: on a timeout or failed build, the query answers from the stale index and the notice still rides along.
- A background `keep_current` loop (`server.py:1538`) calls `refresh_touched` periodically for indexes this session has used.
- Writes are refused before touching the index when the code axis fires (`stale_code_refusal`, `freshness.py:531`, called at `server.py:2278`). `force=True` does not bypass this.

**What the caller does**

1. Read the `staleness` block and the `axis` on each notice. Do not treat an empty answer as proof of absence while `data` is set.
2. `data` only: call `index(action='refresh')`. The refresh is incremental, and the message quotes its measured cost. Usually the query path has already done it.
3. `schema`, server older than index, or `code`: restart the MCP client. Rebuilding does nothing for these, and the message says so.
4. `schema`, index older than server: `index(action='refresh', force=True)`.

**One thing I'd flag:** the data axis uses mtime, and `freshness.py`'s own docstring explains why mtime is wrong for the code axis. A `git checkout` or `touch` that leaves content identical still marks the index data-stale and triggers a refresh. The cost is an unnecessary incremental rebuild, not a wrong answer. `IndexCache` already treats sha256 as the authority, so the same rule could apply here. I did not run anything to confirm the rebuild cost, so that part is from reading the code.