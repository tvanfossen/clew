The index knows it is out of date through three separate checks, one per axis. It reports that to the caller on every reply, and the caller's fix depends on which axis is stale.

**How it knows.** `index(action='status')` reads the database and the source tree:

- **data:** the database is older than the source. `db_status` counts `source_changed_files` and reports the newest changed source file. Sources newer than the database mean a rebuild fixes it. Version numbers alone cannot catch this. A test notes that an earlier version check missed source drift entirely, so the check uses file mtimes.
- **code:** the running server process loaded its modules at launch. `code_identity()` compares the process fingerprint with the fingerprint of the package source on disk. A mismatch means the server predates its own source. A rebuild through that process would be wrong, because the old pipeline logic would re-stamp the index.
- **schema:** `build_version` versus `expected_build_version`. An index stamped by a newer build than this process expects cannot be cleared by any rebuild through this process.

The current index for this repo reports `stale: false`, `source_changed_files: 0`, `build_version` 9 equal to expected 9, and `matches_source: true`.

**What it tells the caller.** Query replies carry a `staleness` block only when some axis is stale; a current index adds nothing. The notices come from `staleness_notices()`, `_staleness()` and `freshness.notices()`. Each notice names the action that clears it, because the three axes need different actions. The reply also names the `target` it answered from. The measurement is non-raising by contract, so a failure to measure degrades to "no annotation" and never turns a good answer into an error.

**What the caller does.**

| Axis | Meaning | Action |
|---|---|---|
| data | DB older than source | `index(action='refresh')` rebuilds it |
| code | server process older than source | restart the MCP client, then `index(action='refresh', force=True)` |
| schema | index newer than server | no rebuild clears it; the caller cannot fix it from this process |

Some details in that table come from the module docs and are not directly visible in the index. The refresh behaviour follows the code, not the tool description.

- **Queries auto-refresh only the data axis.** `_data_stale()` returns true only for the data axis and is checked only when `matches_source` holds. It never rebuilds through a stale process, which could corrupt the index.
- **Writes are refused on a code-stale process.** `stale_code_refusal()` returns a refusal message that `force` does not override. Reads still work, and read data is live. The module records that a rebuild from a stale process once dropped a whole layer and then reported `stale: false`. Restarting the client is the only fix for the code axis.
- **Background refresh is bounded.** `_refresh_stale()` waits on the build lock for a bounded time, deduplicates concurrent refreshes, and logs failures. Its build call is `_run_build(..., skip_if_fresh=True)`.

**Summary.** The index detects staleness itself on three axes and reports it on each reply, with a per-axis remedy. Queries refresh data automatically. The caller's job is to rebuild for data staleness, restart the client for code staleness, and treat schema staleness as needing a different version of the tool.