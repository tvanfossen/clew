**Short answer:** the index is judged stale on three independent axes. Each one is reported as a `{axis, message}` notice, and each has a different remedy. Two of the three are handled automatically by the server, and the remaining cases tell the caller what to do.

**How it knows** (`clew/mcp_server/state.py:1140` `db_status`, `clew/mcp_server/freshness.py`)

| Axis | Check | Cleared by |
|---|---|---|
| `data` | `_source_drift` (state.py:823) stats each indexed path and counts files whose mtime is newer than the db's. | Rebuild (`index(action='refresh')`) |
| `schema` | `build_version` in the db vs `CLEW_BUILD_VERSION` in the running server. | Rebuild with `force=True` if the index is older. If the index is *newer*, a rebuild cannot clear it. Restart the client. |
| `code` | `source_fingerprint` (freshness.py:112) is a sha256 over the relative path and content of every `.py` in the package. It is taken at import and compared with the disk now. | Only restarting the MCP client |

`stale` in `db_status` is true if the db is missing, the version differs, or `changed > 0`.

**What it tells the caller**

- `freshness.notices()` (freshness.py:573) returns one notice per active axis, or an empty list when current.
- Query replies carry a `staleness` block only when it is non-empty (tools_query.py:1843). A current index adds nothing to the payload.
- A `definitive: not found` note is rewritten when the data or schema axis is stale, because a symbol may post-date the build or a layer may be missing (`_withdraw_definitive`, tools_query.py:257).
- `status` also reports the `code` identity block and the measured cost of a refresh.
- Wording is deliberate. The `code` notice says reads are live and only writes are affected, after an earlier message gave a false all-clear (gh#348).

**What the caller does**

- **Query path (automatic, data axis):** `register_query_tools` awaits `_auto_refresh` before each answer (server.py:611, 1242). It rebuilds under the per-repo build lock with a 120 s bounded wait and a re-check inside the lock. If the rebuild fails, the query answers from the stale index and the notice stays on the reply.
- **Background (automatic):** `keep_current` (server.py:1538) calls `refresh_touched` on each interval for every index the session has touched.
- **Explicit:** the caller reads `staleness` and calls `index(action='refresh')`, using `force=True` for the schema case.
- **Code axis:** the caller restarts the client. Until then, `build_or_refresh` refuses (server.py:2278, `stale_code_refusal`), `force` cannot override the refusal, and `_data_stale` checks `matches_source` first so auto-refresh never attempts a build that could drop layers.

**Limits I noticed reading the code (not run)**

- The `data` axis is mtime-based, while the `code` axis deliberately moved to content hashing because mtime trips on `git checkout`. A checkout can therefore mark the index stale with no content change. The cost is an unnecessary rebuild, not corruption.
- `_source_drift` only stats paths already in the index. A deleted file is skipped (`except OSError: continue`), and a newly added file that was never indexed is invisible to it. Deletions and additions do not raise the `data` axis.
- Future-dated mtimes beyond 300 s are ignored as edits and logged as a warning (state.py:860).