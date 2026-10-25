**Short answer:** the tool compares three things against the current disk, reports the result as a `staleness` block on replies, and for the data axis refreshes itself before answering. The caller's job is mostly to restart the client when the code axis fires, not to rebuild.

**How it knows: three axes** (`clew/mcp_server/freshness.py:2-21`)

| Axis | Check | Where |
|---|---|---|
| `data` | Any indexed source file whose mtime is newer than the database's mtime | `_source_drift`, `clew/mcp_server/state.py:823-882` |
| `schema` | Stamped `build_version` differs from `CLEW_BUILD_VERSION` | `db_status`, `state.py:1140-1233` |
| `code` | SHA-256 over the relative path and content of every `.py` in the running package, compared with the fingerprint taken at process start | `source_fingerprint` and `code_identity`, `freshness.py:112-242` |

`db_status` sets `stale` if the database is missing, the build version is wrong, or any source file has changed. It also reports `source_changed_files`, `newest_changed_source`, the measured cost of the last refresh, and a `code` block.

**What it tells the caller**

- Every query reply names its `target`. It carries a `staleness` list only when some axis is active (`tools_query.py:1841-1844`). A current index adds nothing.
- Each notice has an `axis` and a message that names the action that clears it (`freshness.py:381-484`).
- When the schema axis is active, a "definitive empty" answer is rewritten to say it is not definitive and to refresh first (`tools_query.py:194-268`). On a subject miss under the data axis, the wording is the same. The data-axis case is an inference from the code's comments, not something I ran.

**What the caller does, per axis**

- **data:** the query path refreshes first. `_auto_refresh` (`server.py:1242-1285`) takes a bounded build lock, re-checks inside it so concurrent queries collapse into one build, and runs the incremental refresh. If the refresh fails or the lock wait times out, the query answers from the old index and the notice stays on the reply. The caller can also call `index(action='refresh')`, with `force=True` for a full rebuild.
- **schema, index older than server:** `index(action='refresh', force=True)`.
- **schema, index newer than server:** a rebuild cannot clear it, because it re-stamps the same newer version. The caller must restart the MCP client (`freshness.py:412-442`).
- **code:** a rebuild cannot fix it. The caller must restart the client. Until then, writes are refused: `stale_code_refusal` is checked in `_first_build_refusal` (`server.py:1393`) and before builds. Reads stay live because each query opens the database fresh. `force=True` does not get past this refusal (`freshness.py:531-564`).
- **The caller's own rule** (from the wording in `tools_query.py:216-221`): if an answer says something is missing and a data notice is present, refresh and ask again before concluding it does not exist.

**Caveats I found**

- The data axis uses mtimes (`state.py:842-873`). `freshness.py:116-129` says mtimes are wrong for the code axis because `git checkout` and `touch` change them without changing content. The same objection applies to data drift, so a checkout can trigger a refresh that does no real work. I did not check whether the refresh itself skips unchanged content.
- Incremental refresh has limits. A newly added cross-file call in Python or Rust waits for a full rebuild, and a call that needs two new hops does too (`README.md:122-129`).
- A stale process reads live data but writes old logic, which is why the write refusal exists (`freshness.py:30-40`).