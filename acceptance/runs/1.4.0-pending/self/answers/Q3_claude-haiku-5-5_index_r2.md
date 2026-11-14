**Short answer:** the index compares itself against two things, the sources on disk and the running server's own code. It reports the result on every query reply as a `staleness` list, one entry per axis, and it tries to fix the data axis itself. The caller's job is mostly to act on the axis named in the notice, because the other two axes cannot be fixed by a rebuild.

**How it knows (`clew/mcp_server/state.py`, `freshness.py`)**

`db_status(target)` measures three things:
- **Pipeline version:** the `build_version` stamped in the database versus `CLEW_BUILD_VERSION`.
- **Source drift:** `_source_drift` stats each indexed file against the database's mtime and counts the ones newer. It deliberately ignores mtimes more than a small skew tolerance in the future, since those would make the index permanently stale.
- **Code identity:** `code_identity()` compares the process's fingerprint, taken at import, with the fingerprint of the source tree on disk. `matches_source` is false only when both are known and differ.

`db_status` sets `stale` if the database is missing, the version differs, or any source changed. The flag alone does not say what to do about it, so `freshness.notices()` splits the problem into three axes, in order of how often a reader acts on them:

| Axis | Trigger | Remedy stated in the notice |
|---|---|---|
| `data` | `source_changed_files > 0` | `index(action='refresh')` |
| `schema` | stamped version ≠ server version | If the index is newer, restart the client, because a rebuild re-stamps the same version. If it is older, `index(action='refresh', force=True)`. |
| `code` | process fingerprint ≠ source fingerprint | Restart the MCP client. A rebuild cannot fix this. |

`notices()` returns an empty list when the tool is current, so a current index adds nothing to the reply. The repository's index reports `stale: false` right now, so none of these would appear here.

**What the caller gets**

`DocsDbServer.staleness_notices()` (`server.py:1548`) runs on every reply and never raises. `QueryTools._staleness` attaches the notices to the payload and shrinks them to fit the response budget (full prose, then compact, then minimal), so a large answer keeps its warning. A routed reply is annotated only for the repository it actually read.

**What the server does before the caller sees it**

On a query, `_auto_refresh` (`server.py:1242`) checks `_data_stale`. If the data axis is stale, it runs `_refresh_stale` under the repository's build lock, with a bounded wait. Inside the lock it re-checks, so concurrent queries produce one build. The build uses incremental `skip_if_fresh` semantics. If the wait times out, or the build fails, the query answers from the existing index and the notice still rides along. The server refuses to auto-refresh when `matches_source` is false, because an old process rebuilding would re-stamp the index with stale pipeline logic.

**What the caller should do**

1. Read `staleness[].axis` in the reply. A stale-data notice means the answer may describe code that no longer exists. The query may already have refreshed, so the caller should check whether the notice is still present rather than assume.
2. On `data`: call `index(action='refresh')` if the notice remains.
3. On `schema` (server older than index): restart the MCP client. Rebuilding does not clear it.
4. On `schema` (index older than server) or on a missing layer: `index(action='refresh', force=True)`.
5. On `code`: restart the MCP client. Write paths are refused by `stale_code_refusal` (`freshness.py:531`), and `force` deliberately does not bypass that refusal.

**Caveats**

- I read the code and its docstrings through the index. I did not run a stale-index scenario to confirm the behaviour end to end, and I did not read the test files beyond their names.
- `db_status` has a `_source_drift` edge case: a database that cannot be read reports zero drift and falls back to the version check. That is intentional, but a caller should not treat "no data notice" as proof of freshness when the database itself is unreadable. The `stale` flag and `exists` cover that case.