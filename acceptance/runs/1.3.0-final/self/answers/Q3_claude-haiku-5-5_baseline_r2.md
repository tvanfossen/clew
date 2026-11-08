The tool detects staleness on three separate axes, reports each one as a notice that names the action that clears it, and for the data axis it also refreshes automatically before answering. The MCP server (`clew/mcp_server/`) is where this lives. I did not find a separate freshness check on the CLI query path, so treat the caller behaviour below as MCP-specific.

**How it knows**

| Axis | Signal | Where |
|---|---|---|
| `data` | Any indexed source file (`path WHERE type=1`) has an mtime newer than the db file's mtime. Also `stale` if the stamped build version is not current. | `_source_drift` in `clew/mcp_server/state.py` |
| `schema` | `build_meta` build version differs from `CLEW_BUILD_VERSION` in `clew/signature.py`. | `db_status`, `_schema_notice` |
| `code` | The running process's source fingerprint (SHA over `*.py` content, not mtime) differs from the tree on disk, so the server predates its own code. | `code_identity`, `_code_notice` in `clew/mcp_server/freshness.py` |

Two guards keep the data check honest. Source mtimes more than 300 s in the future are ignored, because they would otherwise keep the index stale forever. An unreadable db fails closed to "no drift", since the version term already flags it.

**What it tells the caller**

- `status` / `db_status` returns the raw fields: `exists`, `build_version`, `expected_build_version`, `source_changed_files`, `newest_changed_source`, `stale`, `age_days`, and a `refresh` cost measured from earlier builds.
- Every query reply carries a `staleness` list of `{axis, message}` entries when anything is stale, and omits it when current. Messages are per axis:
  - `data`: "N indexed source file(s) have changed… Call `index(action='refresh')`", with the cost.
  - `schema`, stamped older than the server: rebuild with `force=True`. Stamped newer: rebuilding cannot clear it, so restart the MCP client.
  - `code`: reads are fine but writes are unsafe, so restart the client. A rebuild cannot fix it.
- The axis token survives when the payload is over budget. The prose is compacted in three tiers.

**What the caller does**

1. **Query time.** Before answering, `_auto_refresh` rebuilds a data-stale index, but only if the process `matches_source`. It has a bounded lock wait, and the re-check inside the lock deduplicates concurrent refreshes. A failed refresh never raises: the query answers from the stale index and the notice still rides along. An absent index is built in the background.
2. **Background.** `keep_current` runs `refresh_touched` on a timer, so indexes the session has used are refreshed between queries.
3. **Explicit.** `index(action='refresh')` calls `build_or_refresh`. A `code`-stale process is refused first, and `force` cannot override that. The freshness check then runs inside the per-target lock, so a current index is skipped and not rebuilt. The result includes a measured `duration_ms`, even on a skip.

```
query ──► data-stale && matches_source? ──yes──► refresh under lock ──► answer
              │ no                                   │ fail
              ▼                                      ▼
        absent? → background first build      answer + staleness notice
```

**Caveats I noticed**

- The data check is mtime-based, so `touch` on an unchanged file counts as drift and triggers a rebuild.
- A deleted indexed file is skipped by the drift check, so it does not register as drift. The rebuild itself will notice it.
- I read the code, not the tests, and did not run anything, so the behaviour above is from source and docstrings.