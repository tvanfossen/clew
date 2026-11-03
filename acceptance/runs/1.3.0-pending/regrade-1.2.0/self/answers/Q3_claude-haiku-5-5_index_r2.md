**Short answer:** the index compares its own build against the current source on three separate axes, puts any mismatch into every query reply as a `staleness` block, and in most cases refreshes itself before answering. The caller's job is to read which axis is stale, because only one of them is fixed by a rebuild.

**How it knows (`clew/mcp_server/state.py`, `db_status`):**

- **data:** `_source_drift` stats every indexed source file against the database's mtime and counts the files newer than the build. Mtimes in the future are excluded and logged, so a skewed clock cannot keep an index permanently stale.
- **schema:** the build version stamped in the database is compared with `CLEW_BUILD_VERSION`, the version this server expects.
- **code:** `code_identity()` (`clew/mcp_server/freshness.py`) compares the fingerprint of the source tree on disk with the fingerprint taken when this server process loaded. It reports `matches_source: False` only on positive disagreement, so an unreadable tree does not raise a false alarm.

**What it tells the caller:**

`notices()` (`freshness.py`) turns those checks into a list of `{axis, message}` in the order data, schema, code. The list is empty when the index is current, and `staleness_notices()` in `server.py` attaches it to every query reply. `status` also carries the three measurements and an interpreted `staleness` block, which is absent when current. `_staleness_within_budget` in `tools_query.py` shrinks the notices to fit the response budget rather than dropping them.

The axes have different remedies, and the messages say so:

| Axis | Meaning | Remedy |
|---|---|---|
| `data` | Indexed sources changed since build | `index(action='refresh')`, usually automatic |
| `schema`, index older than server | Index predates this server | `index(action='refresh', force=True)` |
| `schema`, index newer than server | Server predates the index | Restart the MCP client. A rebuild cannot clear it. |
| `code` | Running process predates the source tree | Restart the MCP client. A rebuild is unsafe and cannot fix it. |

**What the caller does:**

1. **Queries:** `_auto_refresh` in `server.py` runs before the answer. If the data axis is stale and the process matches its source, it rebuilds under a per-repository build lock with a bounded wait. Four concurrent stale queries produce one build. A failed or stalled refresh falls back to answering from the existing index, and the staleness block still rides along.
2. **Absent index:** `_first_build_refusal` allows a background first build only for a git work-tree root or a registered repository, and never from a process older than its source.
3. **Writes:** `stale_code_refusal` refuses any write from a stale process. `force` does not override it.
4. **Empty answers:** data staleness does not turn an empty result into a definitive "not found", but a schema-stale index does. The tests `test_a_data_stale_subject_miss_withdraws_the_definitive_claim` and `test_a_schema_stale_index_withdraws_the_definitive_claim` cover this.

**Caveat:** `dossier` flagged anchor mismatches on `_staleness`, `notices` and `_staleness_within_budget`. Their file or line ranges have moved since the index was built, so the line numbers above may be slightly off, though the logic described is what the bodies say.