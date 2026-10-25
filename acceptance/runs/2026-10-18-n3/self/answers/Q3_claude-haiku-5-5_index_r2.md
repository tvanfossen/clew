A clew index can be stale in three independent ways, and the tool reports each one separately because each has a different fix.

**How it knows.** `db_status` (`clew/mcp_server/state.py:1140`) computes staleness from three checks:

- **data**: the database was stamped by an older pipeline build, or source files have changed since the build (`source_changed_files`, `newest_changed_source`).
- **schema**: the database was stamped by a *newer* build than this process expects (`build_version` > `expected_build_version`).
- **code**: this running server process was loaded before the source tree changed. `code_identity()` (`clew/mcp_server/freshness.py:221`) compares the process fingerprint with the current source fingerprint. It only reports a mismatch on positive evidence, meaning both fingerprints are non-empty and they differ. An unreadable tree counts as "cannot tell", not stale.

`notices()` (`freshness.py:575`) turns these into a list of `{axis, message}` entries, ordered data, schema, code. The list is empty when the tool is current.

**What it tells the caller.** Staleness rides in the payload of every query reply, not only in `status`. `staleness_notices()` (`server.py:1548`) runs on the way out of each reply and stamps the notices onto it. A current index adds no field at all, so the signal stays meaningful. The notice text names the remedy for each axis:

| Axis | Meaning | Remedy |
|---|---|---|
| data | Index is older than the source | `index(action='refresh')` |
| schema | Index is newer than this clew build | No rebuild clears it, since a rebuild re-stamps the same newer version |
| code | This server process predates its source | Restart the MCP client, then refresh with `force=True` |

The reply is also non-raising by contract. If measuring staleness fails, the reply is still returned without the annotation, so a good answer never turns into an error.

**What the caller does.**

1. **Automatic refresh on query.** `_auto_refresh` and `_refresh_stale` (`server.py:1294`) rebuild a stale index before answering, but only for the data axis. `_data_stale` (`server.py:1209`) checks `matches_source` first, so an auto-refresh never runs through an out-of-date process, which could re-stamp the index with old pipeline logic. The build takes a per-repo lock with a bounded wait, so one slow build cannot hang the session. If the build fails, the failure is logged and the query is answered from the existing index with its notice still attached.
2. **Write paths refuse on code staleness.** `stale_code_refusal()` (`freshness.py:531`) makes any write return a "REFUSED" message when the process predates its source. `force` does not bypass it. The refusal says to restart the client, then run `index(action='refresh', force=True)`.
3. **Schema staleness is not fixed by refreshing.** It needs a clew build that matches the index.
4. **The caller reads the notice.** A consumer that sees `staleness` on a reply should not treat an empty result as definitive when schema-stale. The test suite checks this (`test_a_schema_stale_index_withdraws_the_definitive_claim`, `test_data_staleness_alone_keeps_the_definitive_claim`).

**Limits of this check.** I read the dossiers for the functions above and not their helper notice builders (`_data_notice`, `_schema_notice`, `_code_notice`), so I have not verified their exact wording. The index flagged `_staleness` and `notices` with `anchor_mismatch`, so their line numbers may be slightly off from the current file.