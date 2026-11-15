**Short answer:** the index does not track its own currency. Each `db_status` call re-measures it from scratch against three independent signals. Each signal is turned into a notice with a named remedy. The server then acts on that differently for each axis: it auto-refreshes for data drift, refuses writes when its own code is stale, and leaves schema mismatches to the caller.

## How it knows

Each call to `db_status` (`clew/mcp_server/state.py`, ~1140) computes:

| Axis | Measured by | Stale when | Cleared by |
|---|---|---|---|
| **data** | `_source_drift` (state.py ~823): stats each indexed source file (`path` rows with `type=1`) and compares its mtime to the db's mtime | any indexed file is newer than the db | rebuild |
| **schema** | `build_version` vs `CLEW_BUILD_VERSION` | stamped version ≠ expected | rebuild if the index is older; **restart the client** if the index is newer (a rebuild re-stamps the same newer version) |
| **code** | `code_identity()` (freshness.py ~221): content hash of the package's `.py` files now vs. the hash taken at process import | the two fingerprints differ | restart the client only |

`stale` is true if the db is missing, the version differs, or `changed > 0`. Each axis is interpreted into a `{axis, message}` notice in `freshness.notices()` (freshness.py ~573), ordered data → schema → code. The notices are empty when the index is current, and the `staleness` key is omitted entirely in that case.

## What it tells the caller

- **Query replies:** `QueryTools._staleness` (tools_query.py ~1884) attaches the notices as a `staleness` key on every reply, including not-found replies. It shrinks the prose to fit the response budget but keeps the axis tokens. When data or schema staleness is present, `_withdraw_definitive` (tools_query.py ~257) removes the "definitely absent" claim, because a miss may just mean the index predates the code.
- **`status`:** the same fields are exposed directly, with a `refresh` block giving the measured cost of the last refresh, so the data notice can quote a real duration.
- **Refusals:** write paths return `REFUSED: …` with the remedy when the process is stale (`stale_code_refusal`, freshness.py ~531).

## What the caller does about it

The server does most of the work itself:

1. **Before each query** (`_auto_refresh`, server.py ~1242): if the data axis is stale and the process matches its source, it runs a rebuild under a per-repo lock. The lock wait is bounded at 120 s, and the build re-checks staleness inside the lock so concurrent queries deduplicate into one build. A failed build degrades to answering from the stale index, with the notice attached.
2. **Between queries** (`keep_current` → `refresh_touched`, server.py ~1506–1538): every 15 s (`CLEW_REFRESH_INTERVAL`, 0 disables) it re-checks the session's touched indexes and rebuilds any that are data-stale. This moves the refresh cost off the next query.
3. **Explicit** `index(action='refresh')` (server.py ~2196): skips if fresh unless `force=True`. It refuses outright when the process predates its source, and `force` cannot override that.

The agent's job is therefore mostly to read the `staleness` block and, for `schema` or `code`, do what the message says: restart the MCP client, or call `refresh(force=True)` for an older index.

## Gaps I found reading the code (not run)

- **Schema-older indexes are not auto-refreshed.** `_data_stale` only looks at the data axis, so an older-version index with no source edits is flagged but never rebuilt automatically. The caller must call `refresh(force=True)`.
- **Deleted and new files are invisible to the data axis.** `_source_drift` iterates only paths already in the index, and it skips files it cannot stat (`except OSError: continue`). A file added to the tree is never counted, and a deleted file doesn't raise staleness.
- **The data axis still uses mtime, while the code axis uses content.** `freshness.source_fingerprint` was changed to hash content because mtime fires on `git checkout` and `touch`. `_source_drift` still compares mtimes, so a checkout that rewrites a file with identical bytes can flag the index stale and trigger a rebuild. The rebuild is incremental, so the cost is small, but the inconsistency is there.