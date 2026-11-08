**Short answer:** clew compares three things, and each one has a different fix. Query replies carry the result as a `staleness` list. Clew refreshes stale data itself before answering, and the caller only has to act on the axes that refresh cannot clear.

**How it knows.** `db_status` in `clew/mcp_server/state.py:1140` computes three axes:

| Axis | Check | Source |
|---|---|---|
| `data` | Indexed source files whose mtime is newer than the database's mtime. Files dated more than 300 s in the future are ignored. | `_source_drift`, `state.py:823` |
| `schema` | `build_version` stamped in the DB vs `CLEW_BUILD_VERSION` | `signature.py`, `state.py:1182` |
| `code` | SHA-256 over the content of every `.py` in the package, compared with a fingerprint taken at process import | `freshness.py:112`, `:221` |

The `code` check is deliberately content-based, not mtime-based, because a `git checkout` or `touch` should not trip a hard gate. It reports "no mismatch" when either fingerprint is empty, since an unreadable tree is not evidence of agreement.

**What it tells the caller.** `freshness.notices()` (`freshness.py:573`) turns the raw fields into `{axis, message}` entries. The list is empty when the index is current, and `db_status` includes a `staleness` key only when it is non-empty. Each message names the action that clears it:
- `data`: call `index(action='refresh')`, with the measured cost from the last refresh.
- `schema`, index older than server: call `index(action='refresh', force=True)`.
- `schema`, index newer than server: a rebuild cannot clear this. The client must restart.
- `code`: a rebuild cannot clear this. Reads are still correct because the DB is opened per call. Writes are refused, and `force` does not override the refusal (`stale_code_refusal`, `freshness.py:531`).

Query replies get the same `staleness` stamp via `server.py:1708`. A subject miss (`found: false`) with a live `data` notice is marked "NOT DEFINITIVE" (`tools_query.py:216`), so a symbol added after the build is not reported as absent.

**What the caller does.**
1. Read the `staleness` list, not the boolean `stale`. Absent means current.
2. Most `data` staleness is handled automatically. Before a query is answered, `_auto_refresh` (`server.py:1242`) rebuilds a data-stale index under the per-repo build lock, with a bounded wait and a re-check inside the lock. If the refresh fails or is refused, the query still answers from the old index and the notice rides along.
3. For `schema` or `code` problems, or when a refresh fails, the caller follows the message above. The caller does not decide whether to rebuild through `code`: the server refuses it.

**Gaps I noticed reading the code** (not run):
- `_source_drift` iterates only paths already in the `path` table. A file added after the build is not counted as `data` drift, so it appears only as a missing symbol.
- The `data` check is mtime-based. A checkout that rewrites files with identical content will still count as drift, and the refresh will then have to re-hash to find nothing changed. The `code` axis avoids this problem and the `data` axis does not.