**Short answer:** clew checks its own currency on three separate axes, attaches the result to every reply, and by default refreshes the data axis itself before answering. The caller is only left with the code and schema axes, which need a client restart or a rebuild that clew refuses to run.

**How it knows (three axes, `clew/mcp_server/freshness.py`)**

- **`data`:** the database is older than the source. `db_status` reports this as `source_changed_files`. The test notes say a version stamp alone cannot see source drift, so this axis is measured from file modification times.
- **`code`:** the running server imported its modules at launch, so a committed fix may not be in its logic. Data is read live, so only the process's logic is stale. `code_identity()` compares the process fingerprint with the on-disk source fingerprint (`matches_source`).
- **`schema`:** `build_version` against `expected_build_version`. An index stamped newer than the server can never be cleared by a rebuild, because the rebuild re-stamps the same newer version.

**What it tells the caller**

- Every query reply carries a `staleness` list of `{axis, message}` notices, but only when something is stale. A current index adds no block, by design. Notices are built by `DocsDbServer.staleness_notices` (`server.py:1548`), which never raises.
- When the schema axis is stale, a definitive-empty answer is rewritten. `_withdraw_definitive` drops "do not retry" and says the result may reflect a missing layer, so the reply stops claiming an empty result is definitive.
- `status` reports the raw `stale` flag unconditionally. The interpretation appears only when there is something to interpret.

**What the caller does**

- **Data axis:** clew handles it automatically. `_answering_with_refresh` wraps each query tool, and `_auto_refresh` calls `_data_stale`, then `_refresh_stale`. The refresh takes the per-repository build lock with a bounded wait, re-checks staleness inside the lock so concurrent sessions deduplicate to one build, and runs the build in a worker thread. If the build fails or the lock wait times out, the query still answers from the index as it stands and the staleness notice remains. The auto-refresh is skipped entirely when the process code does not match its source.
- **Code axis:** clew cannot fix it from inside the session. Restart the MCP client so it loads current code, then run `index(action='refresh', force=True)`. Reads are safe in a stale process. Writes are not: `stale_code_refusal` makes write paths refuse, and `force` does not override that. A stale process once rebuilt an index at an older build version and dropped the `external` stage; that is why writes are refused.
- **Schema axis:** nothing the consumer can do clears it through this process. Use a newer server build, or treat the answers as unearned.
- **Absent index:** `_auto_refresh` starts a background first build, and `_first_build_refusal` covers the write side.

**Caveat:** this comes from the index alone. `_staleness` is flagged as having an anchor mismatch (its body may not match the current file), so the exact sizing logic may have drifted from what I describe. The rest of the answer rests on the docstrings and the tests they cite, which I did not verify against the source.