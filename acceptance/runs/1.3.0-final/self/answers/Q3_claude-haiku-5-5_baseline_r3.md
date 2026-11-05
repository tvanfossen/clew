The tool does not guess from git state. It checks three separate things, reports them as three named axes, and in most cases refreshes the index itself before answering a query. The caller's job is mostly to read the notice and, for two of the three axes, do something a rebuild cannot fix.

**How it knows**

| Axis | Check | Source |
|---|---|---|
| `data` | Any indexed source file (`path WHERE type=1`) has an mtime newer than the database file's mtime. | `_source_drift` in `clew/mcp_server/state.py` |
| `schema` | `build_version` stamped in the DB differs from `CLEW_BUILD_VERSION`. | `read_build_signature` in `clew/signature.py`; `_schema_notice` in `freshness.py` |
| `code` | The running process's source fingerprint, taken at import, differs from the fingerprint of the package source on disk. | `code_identity` in `freshness.py` |

Two details matter. The data check compares mtimes, not content, so a checkout or touch that bumps mtimes counts as drift. Source files dated more than 300 s in the future are ignored, and a warning is logged, because otherwise a skewed clock would keep the index stale forever.

**What it tells the caller**

- `status` returns a `db_status` payload with `exists`, `build_version`, `expected_build_version`, `source_changed_files`, `newest_changed_source`, `stale`, `age_days`, a measured refresh cost, and `code`.
- `stale` is true if the DB is missing, the version differs, or any source changed.
- A `staleness` list appears only when something is stale. Each entry has an `axis` and a `message` that names the remedy. Current indexes get no `staleness` key at all.
- Query replies carry the same `staleness` block and name the target they answered from.

**What the caller does**

Queries refresh first. `_answering_with_refresh` wraps each query tool and calls `_auto_refresh`:

- **Data-stale index:** `_refresh_stale` takes the per-repo build lock, waits up to 120 s, and re-checks inside the lock, so concurrent callers produce one build. If the wait times out or the build fails, the query answers from the old index with its notice attached.
- **Missing index:** a first build starts in the background. The query waits up to 20 s for it and otherwise refuses with a "building" reason. Only one first build runs at a time, with a queue of four.
- **Explicit refresh:** `index(action='refresh')` or `build_or_refresh` runs the same freshness check inside the lock and skips if already current. `force=True` forces a rebuild.

The notice messages tell the caller what to do on each axis:

- **Data:** call `index(action='refresh')`. The incremental cost is quoted.
- **Schema, index older than server:** call `index(action='refresh', force=True)`.
- **Schema, index newer than server:** a rebuild re-stamps the same version and cannot clear `stale`. Restart the MCP client.
- **Code:** only a client restart helps. Data is read live per call, so the query tools are current. Only the process's logic is old.

Writes are refused when the code axis is stale. `stale_code_refusal` returns a `REFUSED:` message, and `force` does not bypass it.

**Caveat:** `AGENTS.md` points callers to `SKILLS.md`, but this run's copy of the repo has no `SKILLS.md`. The caller-side behaviour above comes from the code and docstrings, not from that document.