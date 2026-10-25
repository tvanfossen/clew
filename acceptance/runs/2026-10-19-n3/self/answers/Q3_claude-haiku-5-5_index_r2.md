**How it knows.** Staleness has three independent axes, computed on every reply.

| Axis | Measured in | Signal | Cleared by |
|---|---|---|---|
| `data` | `_source_drift` (`clew/mcp_server/state.py:823`) | Indexed source files whose mtime is newer than the database's. Future-dated mtimes are ignored so a skewed clock can't force permanent staleness. | `index(action='refresh')` |
| `schema` | `_schema_notice` (`freshness.py:412`) | The build version stamped in the index differs from `CLEW_BUILD_VERSION`. | Index older than server: `refresh(force=True)`. Server older than index: restart the client. |
| `code` | `code_identity` (`freshness.py:221`) | The source fingerprint captured when this process started differs from the fingerprint of the tree on disk now. `matches_source` is False only on positive disagreement. | Restart the MCP client. A rebuild does not help. |

`db_status` (`state.py:1140`) combines these into a `stale` boolean and an absent-when-current `staleness` block.

**What it tells the caller.** `notices()` (`freshness.py:575`) returns a list of `{axis, message}` ordered data → schema → code, and empty when the index is current. The server attaches that list to every query reply as `staleness` (`tools_query.py:1886`). The annotation is sized to the remaining payload budget, so it is compacted rather than dropped when a reply is large. A routed reply is annotated for the repository it actually read. The measurement never raises, so it cannot turn a good answer into an error. A current index adds no key at all.

**What the caller does.** It reads the axis and acts on the matching remedy:

- **`data`:** call `index(action='refresh')`. The reply quotes the expected cost from the last measured refresh. The freshness check runs inside the per-target lock, so concurrent refreshes produce one build, and a current index is skipped.
- **`schema`, index older than server:** call `index(action='refresh', force=True)`.
- **`schema`, server older than index:** do not rebuild. A rebuild re-stamps the same newer version and never clears the flag. Restart the client.
- **`code`:** restart the MCP client. The query tools open the database per call, so the data itself is current and only the server's logic is old.

Writes are guarded. `build_or_refresh` (`server.py:2199`) calls `stale_code_refusal` (`freshness.py:531`) before the build decision and the lock. If the process predates its source, it returns `REFUSED: … Nothing was written`. `force` cannot override this, so the caller's only path is to restart the client and then refresh.

I read the source and the notice wording directly; I did not run `status` or `refresh` against this index.