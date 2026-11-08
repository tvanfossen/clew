A clew index knows it is stale by comparing three independent measurements, each with its own remedy. The server acts on the first one itself, and the caller is told about the other two.

**How it knows**

| Axis | Detected by | Meaning | Cleared by |
|---|---|---|---|
| `data` | `db_status` (`state.py`): `source_changed_files` from `_source_drift`, plus build-version stamp vs `CLEW_BUILD_VERSION` | Indexed sources changed since the build | Rebuild |
| `schema` | `build_version` vs `expected_build_version` | Index was stamped by a *newer* build than this server expects | Nothing this client can do; a rebuild re-stamps the same newer version |
| `code` | `code_identity()` (`freshness.py`): hash of the package source tree vs the fingerprint taken at process import | The running server predates its own source, so its logic and module constants are old | Restarting the MCP client only |

`db_status` sets `stale` when any of these holds. `staleness` is absent when the tool is current, so it stays a signal. `source_fingerprint` hashes relative paths and file bytes, not mtimes, because mtimes change on `git checkout` with no content change. An unreadable tree yields `""`, which means "cannot tell", not "unchanged". `code_identity` only reports `matches_source: false` on positive evidence of a difference.

**What the caller is told**

`notices()` returns a list of `{axis, message}` entries in the order data → schema → code. It is empty when the index is current. The messages are worded to avoid two wrong conclusions:
- The `data` notice says an answer may describe code that no longer exists and names `index(action='refresh')` with its cost.
- The `code` notice says the *data* is still read live, but the *logic* is old and a rebuild cannot fix it. This is the gh#348 lesson: a notice that said "the data is unaffected" was read as reassurance, and a rebuild then dropped a pipeline layer.

Each query reply carries these notices in its own payload. A reply from a routed repository is annotated only for the repository it actually read. `_withdraw_definitive` also removes a "definitive empty result" claim from replies when the schema axis is set, so a stale index cannot assert that a layer is absent.

**What the caller does**

Two paths, depending on the call:

1. **Queries: the server refreshes first.** `_answering_with_refresh` wraps every synchronous query tool. Before answering, `_auto_refresh` runs `resolve_target` and checks `_data_stale`. That check returns true only when the data axis is stale and the `code` axis matches, so a stale process never rebuilds. If the index is stale, `_refresh_stale` takes the per-target build lock with a bounded wait. It re-checks staleness inside the lock, so concurrent sessions produce one build. A failed or stalled refresh degrades to answering from the old index with its notice attached. An absent index is built in the background.
2. **Writes: the server refuses.** `stale_code_refusal()` runs before any build. If the process predates its source it returns a `REFUSED:` message, and `build_or_refresh` checks it ahead of the build decision. `force=True` does not get past it. The caller is told to restart the client and then run `index(action='refresh', force=True)`.

The caller's remaining job is to act on the notice text. For `data`, a query already triggered the refresh if it was allowed to. For `schema`, there is no fix from this side. For `code`, restart the client. If the caller wants the detail, `index(action='status')` returns the full diagnosis, though the docs say not to open a session with it.

**Limits of this answer**

- The current index for this repository reports `stale: false`, `source_changed_files: 0`, build 9 of 9, so I could not observe a stale case live.
- The dossiers for `staleness_notices`, `_staleness` and `build_or_refresh` came back with `anchor_mismatch: true`, meaning the index's line anchors no longer match the file. I relied on their docstrings and the named callees for those, not on the verbatim bodies.
- I did not run the test suite. The relevant tests include `tests/test_freshness.py` and `test_build_or_refresh_refuses_when_the_process_predates_its_source`.