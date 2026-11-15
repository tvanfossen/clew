A clew index can be stale on three independent axes. The tool detects each one differently, reports them as a `staleness` list on every query reply, and the caller's remedy depends on which axis fired. The axis logic lives in `clew/mcp_server/freshness.py`, the detection in `state.py`, and the refresh and reply plumbing in `server.py` and `tools_query.py`. I read the code and did not run the tests.

**How it knows**

| Axis | Detected by | Meaning |
|---|---|---|
| `data` | `state._source_drift`: stats each indexed source file and counts those with mtime newer than `clew.db` | Sources changed since the build. Reads answer from current data, but the index is out of date. |
| `schema` | `build_version` (stamped in the db) vs `CLEW_BUILD_VERSION` (this server) | The index was built by a different pipeline version. |
| `code` | `freshness.source_fingerprint`: sha256 over relative path and bytes of every `*.py` in the package, compared with the fingerprint taken at process import | The running server process predates the source tree, so its logic is old. |

Two details matter. The data axis uses mtime, but a future-dated mtime more than 300 s ahead is ignored, so a skewed clock cannot keep the index stale forever. The code axis hashes content rather than mtime, because a `git checkout` that restores identical bytes should not trip a safety gate.

**What the caller sees**

- `db_status` carries `stale`, `source_changed_files`, `newest_changed_source`, `build_version`, `expected_build_version`, and a `code` block (`process_fingerprint`, `source_fingerprint`, `matches_source`).
- Every query reply gets a `staleness` list of `{axis, message}`, and the key is absent when the index is current. The README states this as the contract.
- On a subject miss with a `data` notice, the reply withdraws its "definitive" wording. With a `schema` notice it says a layer may be missing rather than empty.
- A write refused by the `code` axis returns `ok: false` with a message starting `REFUSED:`, and nothing is written.

**What the caller does**

1. **`data`:** queries normally refresh first. `_auto_refresh` calls `_data_stale`, then `_refresh_stale`, which is an incremental splice under a bounded build lock with a re-check inside it. A notice that survives into the reply means that refresh was skipped or failed, and the message says to call `index(action='refresh')`.
2. **`schema`, index older than server:** this axis does not auto-refresh, because `_data_stale` looks only at the data axis. The caller must call `index(action='refresh', force=True)`.
3. **`schema`, index newer than server:** a rebuild re-stamps the same newer version, so the flag cannot be cleared from the consumer's side. The fix is to restart the MCP client.
4. **`code`:** reads are unaffected, since they open the db per call. Writes are refused, and `force` does not override the refusal. The fix is to restart the MCP client, then run `index(action='refresh', force=True)`. A rebuild alone does not clear it.

A background `keep_current` loop also refreshes sessions' touched indexes between queries, so the next query usually finds nothing to do.

**Gaps to be aware of**

- The data axis is mtime-based, so `git checkout` or `touch` can mark an index stale even when content is identical. The cost is one unnecessary incremental refresh, not a wrong answer.
- A index stamped by an older pipeline with no source changes will not auto-refresh. It is flagged `stale` and the caller has to force the refresh.