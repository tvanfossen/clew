A clew index can be stale on three independent axes, and each axis has a different cure. The tool measures them, puts the diagnosis in the reply, and the caller's job is to pick the cure that matches the axis.

**How it knows**

- **Data axis (sources changed).** `db_status` in `clew/mcp_server/state.py` counts indexed source files whose content has drifted since the build. `stale` is true when the index does not exist, the build stamp differs from the server's expected version, or `source_changed_files > 0`.
- **Schema axis (build version).** `build_version` is compared with `CLEW_BUILD_VERSION`. The direction matters: an index stamped by a newer build than the server means the server is old.
- **Code axis (running process).** `code_identity()` in `clew/mcp_server/freshness.py` compares a fingerprint taken at import (`PROCESS_SOURCE_FINGERPRINT`) with the current source tree. `source_fingerprint()` hashes relative paths and file contents, not mtimes, so a `git checkout` that restores identical bytes does not trip it. An unreadable tree returns `""`, which means "cannot tell", never "unchanged". `matches_source` is false only on positive evidence of disagreement.

**What it tells the caller**

`notices()` in `freshness.py` builds a list of `{axis, message}` entries in the order data, schema, code. Each message names the action that clears it:

| Axis | Trigger | Remedy stated |
|---|---|---|
| `data` | `source_changed_files > 0` | `index(action='refresh')`, with the cost attached |
| `schema` (index older) | `build_version < expected` | `index(action='refresh', force=True)` |
| `schema` (index newer) | `build_version > expected` | Restart the client. A rebuild cannot clear it. |
| `code` | fingerprints disagree | Restart the client. A rebuild cannot clear it. |

The notices are attached to every query reply through `staleness_notices()` in `clew/mcp_server/server.py` and the `_staleness` method in `tools_query.py`. The block is absent when the index is current, so its presence is a signal. A payload that is already large gets a compacted notice rather than none, through three size tiers in `_staleness_within_budget`. The provider never raises, so a failed measurement cannot turn a good answer into an error. A routed reply is annotated only for the repository it actually read.

A query-time check also runs before answering. `_auto_refresh` in `server.py` rebuilds a data-stale index first, and builds an absent one in the background. `_data_stale` returns false unless `matches_source` is true, so an auto-refresh never runs through an old process. `_refresh_stale` takes the per-repository build lock with a bounded wait, re-checks staleness inside the lock so concurrent queries deduplicate to one build, and degrades to answering from the stale index with its notice if the build fails or stalls.

**What the caller does**

1. Read `staleness` in the reply, or call `status` for the full diagnosis.
2. For a `data` notice, call `index(action='refresh')`. Queries normally do this themselves.
3. For a `schema` notice with an older index, call `index(action='refresh', force=True)`.
4. For a `code` notice, or a `schema` notice where the index is newer, restart the MCP client. Rebuilding is refused in that state.
5. Do not rebuild through a stale process. `stale_code_refusal()` returns a refusal message, and `build_or_refresh` calls it before touching an index. `force` does not override it. The reply states that nothing was written.

The code notice says the query tools are still reading live data, so data changes appear immediately. What is stale is the process's logic and module constants, and the notice is worded so that a reader does not conclude either "my fix failed" or "a rebuild is safe".

Caveat: several of the dossiers returned `anchor_mismatch: true`, so some line numbers may be off by a few lines. The names and behaviour are unaffected.