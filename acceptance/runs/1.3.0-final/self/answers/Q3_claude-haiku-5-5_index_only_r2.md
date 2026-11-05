The index can tell it is out of date on three separate axes. Each axis has a different cause and a different fix, so the caller has to act differently for each.

**How it knows**

`clew/mcp_server/freshness.py` measures the axes. `db_status` in `clew/mcp_server/state.py` gathers the raw facts, and `code_identity()` supplies the code axis.

| Axis | Measured by | Meaning | Clearing action |
|---|---|---|---|
| `data` | `source_changed_files` from `db_status` (indexed sources changed since build) | The index describes code that no longer exists | `index(action='refresh')` |
| `schema` | `build_version` vs `CLEW_BUILD_VERSION` | Index and server were built by different pipeline versions | Index older than server: `index(action='refresh', force=True)`. Index newer than server: nothing the caller can do, because a rebuild re-stamps the same newer version. Restart the client. |
| `code` | `code_identity()` compares the process's fingerprint, taken at import, with a fingerprint of the source tree on disk | The running server loaded old logic and module constants | Restart the MCP client only. A rebuild does not help. |

`code_identity()` reports `matches_source: False` only when both fingerprints are known and differ. If the tree can't be read, it reports True, so an unknown state does not trigger a warning.

**What it tells the caller**

- **Reply payloads.** `DocsDbServer.staleness_notices()` in `clew/mcp_server/server.py` attaches a list of `{axis, message}` to query replies. The list is empty when the index is current, and the `staleness` key is absent in that case. Each message names the action that clears it.
- **Status.** `db_status` reports `stale` and includes an interpreted `staleness` block.
- **Misses.** When a symbol lookup misses on a stale index, the reply adds `_UNEARNED_BY_DRIFT` text: the symbol may be missing because it was added after the build, so refresh and ask again before concluding it doesn't exist.
- **Reads vs writes.** The code-axis message says the query tools read the database live, so data is current for reads. A stale process must not write, though. Its build logic is old, and a build through it can silently drop layers while reporting health.

**What the caller does**

1. **Queries refresh automatically when the problem is `data` only.** `_data_stale()` checks the code axis first. If the process matches the source, it returns true only when the data axis is stale. `_refresh_stale()` then rebuilds under the repository's build lock. The lock wait is bounded, so a slow build cannot hang the session, and a failed build is logged rather than discarded. The reply still carries its notice.
2. **Between queries, `refresh_touched()` keeps the session's indexes current** and runs off the event loop.
3. **Writes are refused on a stale process.** `stale_code_refusal()` must be called before any write path touches an index. It has no override, and `force` does not bypass it. The refusal text tells the caller to restart the client and then run `index(action='refresh', force=True)`.
4. **For `schema` or `code` problems**, the caller follows the notice's action: restart the client, or force-refresh an older index. Retrying a refresh cannot clear a `code` or newer-schema problem.

**Caveats from the index**

- `notices` and `_staleness` are flagged `anchor_mismatch`, so their line numbers may not match the current file. Their logic was not checked against the working tree.
- The replies I got from this index carried no `staleness` block, so the index was current as far as those replies show. I did not call `index(action='status')`.