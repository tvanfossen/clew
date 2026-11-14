**Short answer:** the index checks its own currency on three axes, every query reply carries a notice for any axis that is off, and for the data axis the server refreshes the index itself before answering. The caller only has to act on the other two.

**How it knows.** `db_status` (`clew/mcp_server/state.py:1140`) measures three things and sets `stale` if any is true:

| Axis | Measured by | Stale when |
|---|---|---|
| `schema` | `build_version` stamped in the db vs `CLEW_BUILD_VERSION` | the stamp differs from this build |
| `data` | `_source_drift` (`state.py:823`) stats every indexed file against the db's mtime | one or more indexed sources are newer than the db (future-dated mtimes are ignored) |
| `code` | `code_identity` (`freshness.py:221`) compares the running process's source fingerprint with the source tree's | the package source changed after this process loaded |

A `code` mismatch means the server process is old, not the index. Only a client restart fixes it.

**What it tells the caller.** `notices()` (`freshness.py:575`) returns a list of `{axis, message}`, ordered data → schema → code, and is empty when the index is current. A current index gets no annotation at all, by design. Each message names the remedy:

- **data:** "N indexed source file(s) have changed… call `index(action='refresh')`", with the measured cost of the refresh.
- **schema, index newer than server:** rebuilding cannot clear it; restart the MCP client.
- **schema, index older than server:** `index(action='refresh', force=True)`.
- **code:** the logic may predate the working tree; a rebuild cannot fix it; restart the client.

The notices ride on every query reply through `staleness_notices` (`server.py:1548`) and `_staleness` (`tools_query.py:1886`). They are sized to whatever room the payload leaves and degrade to shorter forms rather than being dropped. Measurement never raises, so a failed check cannot turn a good answer into an error.

**What the caller does.**

1. **The server acts first on data staleness.** `_auto_refresh` (`server.py:1242`) runs before each query. If `_data_stale` is true, it calls `_refresh_stale` (`server.py:1294`), which takes the per-repo build lock with a bounded wait, re-checks staleness inside the lock so concurrent queries produce one build, and builds with `skip_if_fresh`. A failed build is logged and the query answers from the stale index, which still carries its notice. An absent index gets a first build the same way, subject to `_first_build_refusal` (`server.py:1368`).
2. **The caller handles the rest.** It reads the notice and does what it says: an explicit refresh for schema-older-index, a client restart for code and schema-newer-than-server. It should not treat a stale answer as current.
3. **Write paths refuse on the code axis.** `stale_code_refusal` (`freshness.py:531`) refuses any write when the process predates its source. `force=True` does not bypass it, because the incident that motivated the guard used `force`.

**Current state of this repo.** `index(action='status')` reports `stale: false`, `build_version` 9 against 9, `source_changed_files` 0, and `matches_source` true. A query here would carry no staleness notice.

**Caveat.** The dossier flagged `anchor_mismatch` on `_staleness` and `_staleness_within_budget`, so their line numbers may be a few lines off from the current source. Their behaviour as described above is unaffected.