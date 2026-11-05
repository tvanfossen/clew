A clew index can go stale in three independent ways, and each query reply reports which of them applies. The tool both reports the staleness and, for the most common case, fixes it before answering. The caller only has to act in the cases the tool cannot fix itself.

**How it knows**

Staleness is measured on three axes by `db_status` (`clew/mcp_server/state.py`) and `notices` (`clew/mcp_server/freshness.py`):

- **data:** the index is older than the source. `db_status` checks whether source files have changed since the build (file mtimes, not just the version stamp). This is the common case, for example editing a file without rebuilding.
- **schema:** the index was stamped by a newer build than this process expects. A rebuild re-stamps the same newer version, so it cannot clear this.
- **code:** the running server process predates the source tree. `code_identity()` compares the process fingerprint with the current source fingerprint. It reports `matches_source: false` only on positive evidence that the two differ. An unreadable tree counts as a match, so the tool does not raise false alarms.

**What it tells the caller**

- `staleness_notices()` (`server.py`) returns a list of `{axis, message}`. It is empty when the index is current. The list is ordered data, then schema, then code.
- The notices ride in the payload of every query reply, as a `staleness` block. It is absent when current. `_staleness` and `_staleness_within_budget` (`tools_query.py`) size the text to fit. When the payload is large they fall back to a compact message, "stale — call status" at minimum.
- A query against a non-definitive miss carries a warning, `_UNEARNED_BY_DRIFT`. It says a symbol that is missing may be missing only because the index is stale, and that the caller should refresh and ask again before concluding the symbol does not exist.
- `index(action='status')` returns the full diagnosis, including `stale`, `build_version` against `expected_build_version`, `source_changed_files`, `newest_changed_source`, and `code.matches_source`. The design says not to open a session with it, because each reply already reports its own staleness.

**What the tool does about it**

- **Data staleness is fixed automatically.** `_answering_with_refresh` wraps each query tool. Before answering, `_auto_refresh` checks the target (and sub-index, when one is named). If `_data_stale` is true, `_refresh_stale` rebuilds the index under the repository's build lock, with a bounded wait (`_LOCK_WAIT_SECONDS`). The rebuild is deduplicated: after the lock is acquired, it re-checks staleness, so concurrent queries produce one build. A failed or stalled refresh falls back to answering from the existing index, with the notice attached. An absent index is built in the background.
- **Schema and code staleness are never auto-refreshed.** `_data_stale` returns false if `matches_source` is false. A build through an outdated process would run old pipeline logic and re-stamp the index with it, dropping layers. `stale_code_refusal` (`freshness.py`) refuses writes in that case, and `force=True` does not bypass the refusal.

**What the caller does**

1. Normally nothing. A data-stale query refreshes itself before answering.
2. If a reply still carries a data notice, the refresh did not run or failed. The caller should call `index(action='refresh')` and ask again. Do not conclude a symbol is absent from a miss while the notice is live.
3. For a schema notice, a rebuild does not help. The caller needs to check the index against the expected build version.
4. For a code notice, the caller restarts the MCP client so the process loads the current code, then calls `index(action='refresh', force=True)`. A rebuild from the stale process is refused.

**Caveats**

These answers come only from the index. I did not read the source files. Several dossier results carried `anchor_mismatch: true` (for example `_staleness`, `test_build_or_refresh_refuses_when_the_process_predates_its_source`, and `notices`), which means the file changed after the index was built. Their line numbers and bodies may not match the current source. The behaviour described above is from the docstrings, bodies and tests the index returned, so it should be confirmed against the source if you depend on exact details.