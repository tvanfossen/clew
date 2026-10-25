A clew index can be out of date on three independent axes. The tool detects each one, attaches a notice to every query reply, and only acts itself on one of them. The caller's job depends on which axis fired.

**How it knows**

`db_status` (`clew/mcp_server/state.py`) computes the data and schema axes. `code_identity` (`clew/mcp_server/freshness.py:221`) computes the code axis.

| Axis | Detected when | Meaning |
|---|---|---|
| `data` | Any indexed `.py`/source file's fingerprint has changed since the build (`source_changed_files > 0`) | The index describes old source. The query tools open the database per call, so the data is current once a rebuild lands. |
| `schema` | `build_version != CLEW_BUILD_VERSION` | The index was stamped by a different pipeline version. If the index is newer than the server, a rebuild cannot clear it. |
| `code` | The running process's fingerprint differs from the on-disk source fingerprint | The server process loaded old logic at launch. Only a client restart replaces it. |

`code_identity` sets `matches_source` to false only when both fingerprints are non-empty and differ. An unreadable tree counts as "cannot tell", not as stale, so it does not produce a false warning.

**What it tells the caller**

`staleness_notices` (`server.py:1548`) returns a list of `{axis, message}` and is empty when the index is current. Each reply is stamped with that list under a `staleness` key, and `_staleness_within_budget` (`tools_query.py:160`) shrinks the prose to fit the response size. The notice is non-raising: a failure to measure just drops the annotation rather than failing the query. Each message says what to do:

- **data:** "N indexed source file(s) have changed… call `index(action='refresh')`", with the measured cost.
- **schema:** the direction decides the advice. If the server is older than the index, it says to restart the client, because rebuilding cannot clear it. If the index is older, it says to call `index(action='refresh', force=True)`.
- **code:** restart the MCP client. It says a rebuild cannot fix this, and that the data itself is not stale.

**What the caller does**

- **data:** The tool acts on this one itself. `_auto_refresh` (`server.py:1242`) runs before each query. If the index is data-stale and the process matches its source, it rebuilds under a per-repo build lock with a bounded wait. A re-check inside the lock deduplicates concurrent refreshes. A failed build is logged and the query answers from the stale index, with the notice still attached.
- **schema:** The tool does not auto-fix an older index. The notice tells the caller to run `index(action='refresh', force=True)`.
- **code:** The caller restarts the MCP client. `stale_code_refusal` (`freshness.py:531`) then refuses every write from the stale process, and `force` does not bypass it. Reads still work.

So the caller's real obligations are: read the `staleness` block on any reply it intends to act on, let the data axis self-heal, and for schema or code, follow the one remedy the notice names. A rebuild is not a fix for the code axis.

**Caveat:** Some of the dossier results I read (`_staleness`, `notices`, `check_version_staleness`, `_staleness_within_budget`) came back with `anchor_mismatch: true`. That means the file changed since the index was built, so the line ranges and bodies I quoted may not match the current source. The behaviour described above is from the index's view, and I did not read the live files to confirm it.