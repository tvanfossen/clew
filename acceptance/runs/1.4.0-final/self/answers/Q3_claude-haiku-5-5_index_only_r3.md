A clew index can go stale on three separate axes, and the tool both reports them and, for queries, usually fixes the data axis before answering.

**How it knows (`clew/mcp_server/freshness.py`, the `AXIS_*` constants)**

| Axis | Meaning | Cleared by |
|---|---|---|
| `data` | The database is older than the source files. Reported by `db_status` as `source_changed_files`. | A rebuild |
| `code` | The running server process imported its modules at launch, so a committed fix isn't in its logic yet. | Restarting the client only |
| `schema` | `build_version` differs from `expected_build_version`. If the index is *newer* than the server, a rebuild re-stamps the same newer version, so the flag can never clear. | Not clearable by a rebuild in that case |

The `data` check is the one the server acts on: `_data_stale` is compared on each query. The `code` axis came from a real incident (gh#348). A build-30 process rebuilt a build-32 index at version 30, dropped the `external` stage, and then `status` reported it healthy. The fix made `build_or_refresh` refuse via `stale_code_refusal`, which runs before the build decision so `force` can't override it.

**What it tells the caller**

- `DocsDbServer.staleness_notices()` (`server.py`) turns `db_status` into `{axis, message}` pairs. It never raises; any failure yields no annotation.
- `QueryTools._staleness()` attaches those notices to every query reply, sized to fit the payload. Routed replies are annotated only for the repository they actually read.
- `_withdraw_definitive` (`tools_query.py`) removes an unearned "this is a definitive empty result" claim when the schema axis is stale, because a missing layer could make an empty answer false. For the data axis it only does this on a subject miss, since the symbol may postdate the build.
- The messages say which action clears each axis, and the code notice says that only restarting the client helps.
- `status` reports `stale` unconditionally. Its interpretation block appears only when there is something to interpret.

**What the caller does**

The caller usually does nothing. `_answering_with_refresh` wraps each query tool. Before answering, `_auto_refresh` does this:

1. If the data axis is stale, it calls `_refresh_stale`. That takes the per-target build lock with a bounded wait, re-checks staleness inside the lock so concurrent callers produce one build, and runs an incremental build with `skip_if_fresh=True`.
2. If the database is missing entirely, it starts a background first build (`_await_first_build`).
3. On failure, or if the lock wait times out, it answers from the existing index and the staleness notice still rides along.

The explicit `index(action='refresh')` (`build_or_refresh`) is the manual path. It returns a measured `duration_ms`, honours `force`, and refuses on a code-stale process. The remedy for a `code` or `schema` notice is outside the index: restart the client, or rebuild against a matching server.

**Caveats**

- A query-triggered refresh is incremental and deduplicated. It is not guaranteed to be instant, and a slow build can leave the reply answered from the old index, with the notice attached.
- I read the `build_or_refresh` and `_staleness` bodies through the index. Both carry an anchor mismatch or truncation, so the exact lines may have drifted since the index was built.