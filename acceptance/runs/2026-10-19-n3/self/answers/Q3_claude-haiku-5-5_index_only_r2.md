A clew index knows it is out of date by comparing three separate measurements, and each one has a different remedy. The tool does not treat "stale" as one flag.

**How it knows.** Staleness is measured on three axes:

| Axis | Meaning | Detected by | Can a rebuild fix it? |
|---|---|---|---|
| `data` | The source changed after the build (files edited, added or removed) | Mtimes. The test `test_db_status_detects_source_drift` records that a version check alone can't see this, so `db_status` compares against the source | Yes |
| `schema` | The index was stamped by a build version different from the one this server expects | `read_build_signature` reads the `build_version` row from `build_meta` | Only if the server is the newer one. An index stamped newer than the server stays stale because a rebuild re-stamps the same newer version |
| `code` | This server process is older than the working tree | `code_identity()` and its `matches_source` flag | No, not from this process. A build through an old process runs old pipeline logic and can drop whole layers while reporting healthy (gh#348) |

**What it tells the caller.** Every query reply carries a `staleness` block, and only when the index is actually stale. A current index adds nothing, so the block works as a signal rather than a permanent banner. Each notice names its axis. Two side effects follow:

- **Empty results.** If the schema axis is stale, `_withdraw_definitive` rewrites the reply's note so it no longer claims the empty result is definitive. The schema axis means a layer may be missing. The data axis only withdraws a subject miss, because the symbol may postdate the build.
- **Routed replies.** A reply is annotated only for the repository it actually read, never for the default target. Reporting another repo's staleness would be a warning about a database this reply never opened.

The `status` tool always reports `stale` as a field. It adds the interpretation only when there is something to interpret.

**What the caller does.** The design moved the fix into the server, so the caller mostly does not have to act:

1. **Data-stale index: the query refreshes it first.** `_answering_with_refresh` runs `_auto_refresh` before the query. It calls `_data_stale`, which only passes when the code axis is clean (`matches_source`) and the data axis is stale. Then `_refresh_stale` rebuilds under the per-target build lock, and the lock is bounded by `_LOCK_WAIT_SECONDS`. Concurrent queries produce one build: the others re-check inside the lock and skip.
2. **Failed or stalled refresh: answer anyway, with the notice.** A refresh failure is logged and the query answers from the index as it stands. The staleness notice still rides along, so the caller sees the warning.
3. **Schema or code stale: the caller must act, and no rebuild is safe through this process.** `build_or_refresh` refuses before the build decision, and `force` cannot override that. The fix is to restart the client so the server matches the source, or to rebuild with a matching build.
4. **Absent index: built in the background** (gh#48). A query against a missing index starts a first build rather than refusing.
5. **Explicit refresh.** `index(action='refresh')` is the manual path. It reports `duration_ms` measured for that call, and the skip path also reports a duration. The README advises against opening a session with `index(action='status')` because each reply already names its target and flags staleness.

**Caveats.** I read the design from the dossiers on `_auto_refresh`, `_data_stale`, `_refresh_stale`, `_answering_with_refresh`, `_withdraw_definitive`, `read_build_signature` and `build_or_refresh`, plus search hits in the README and `freshness.py` documentation. The index does not contain `clew/mcp_server/freshness.py` itself, so I could not confirm its contents directly. The README's "Refreshing an index" section appeared only as a search snippet, and I did not read it in full.