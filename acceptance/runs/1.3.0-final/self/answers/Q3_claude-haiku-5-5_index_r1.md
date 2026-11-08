**Short answer:** the index can tell it is stale on three separate axes. Query replies carry a `staleness` block naming whichever axes are active. For the data axis, the server usually refreshes before answering, so the caller rarely has to act. The other two axes need the caller to restart the MCP client or force a rebuild.

**How it knows (`clew/mcp_server/state.py`, `freshness.py`)**

`db_status(target)` measures the database and sets `stale` when any of these is true:
- the database file is missing,
- its build stamp differs from `CLEW_BUILD_VERSION`,
- or `_source_drift` finds indexed source files changed since the build (`source_changed_files`, `newest_changed_source`).

`freshness.notices(status, identity)` turns that into named axes, in this order:

| Axis | Detected from | Meaning | Who clears it |
|---|---|---|---|
| `data` | `source_changed_files > 0` | Sources changed since the build; answers may describe code that no longer exists | `index(action='refresh')` |
| `schema` | stamped build version ≠ expected | Index is older than the server (rebuild with `force=True` fixes it) or newer (rebuilding cannot clear it) | Rebuild for older; restart client for newer |
| `code` | `code_identity().matches_source` is false | The running process loaded clew before the package source on disk changed | Only a client restart; a rebuild is not safe |

An empty list means current. The docstring says this is deliberate, because an always-present warning gets ignored. `staleness` is absent from the payload when nothing is stale.

**What the caller gets**

`DocsDbServer.staleness_notices()` (`server.py`) runs on the way out of every query reply and returns the `{axis, message}` list. `QueryTools._staleness()` attaches it to the payload and shrinks it to fit a size budget. Two rules matter:
- A routed reply is annotated only for the repository it actually read, not for the default target.
- The provider never raises. If measurement fails, the reply goes out without a notice rather than turning into an error.

The messages are written to stop misreading. For example, the code notice says the data is not stale and a rebuild is not safe, and the schema notice says which direction the mismatch runs.

**What the server does before the caller acts**

This is the part the question was after. `_auto_refresh` (`server.py`) runs before a query is answered:
- If `_data_stale()` is true, it calls `_refresh_stale()`. That method takes the per-repository build lock with a bounded wait, re-checks staleness inside the lock so concurrent queries produce one build, and runs `_run_build(..., skip_if_fresh=True)`.
- `_data_stale()` returns false if the process does not match its source. That keeps an old server from running a build that could drop layers.
- If a build fails or the lock wait times out, the query still answers from the index as it stands, and the notice rides along.
- If the database is absent, it starts a first build in the background.

**What the caller still has to do**

- **Data axis:** normally nothing; the query has already refreshed it. Calling `index(action='refresh')` explicitly is still available.
- **Schema axis, older index:** call `index(action='refresh', force=True)`.
- **Code axis, or schema axis with a newer index:** restart the MCP client so it loads current code. Write paths refuse until then. `stale_code_refusal()` is called by `build_or_refresh` and `_first_build_refusal`, and it does not accept an override; `force` does not bypass it.

**Caveats**

- The `_staleness` dossier shows `anchor_mismatch: true`, so its line range may have moved since the last build. I read its docstring and not its current body, so I did not verify that exact span.
- I did not run the tests or a live server; this is from the index's dossiers and the bodies it returned.