**How it knows.** `db_status` (`clew/mcp_server/state.py:1140`) measures the database and sets `stale` when any of three things holds: the database is missing, its stamped `build_version` differs from `CLEW_BUILD_VERSION`, or `source_changed_files > 0` (sources drifted since the build). `code_identity()` separately checks whether the running server process matches the source tree. `notices()` (`clew/mcp_server/freshness.py:575`) turns those measurements into up to three axis notices, `data`, `schema` and `code`, and returns an empty list when the index is current.

**What it tells the caller.** Staleness rides in the payload rather than waiting for someone to call `status`. `staleness_notices()` (`clew/mcp_server/server.py:1548`) is stamped onto query replies as `{axis, message}` entries, sized to fit the reply budget. Each message says what to do:

| Axis | Meaning | Advice in the message |
|---|---|---|
| `data` | Sources changed since build | `index(action='refresh')`, with the measured cost |
| `schema`, index older than server | Layers may be missing | `index(action='refresh', force=True)` |
| `schema`, index newer than server | Server is old | Restart the MCP client. A rebuild cannot clear it. |
| `code` | Server process loaded older code than the tree | Restart the MCP client. A rebuild cannot fix it. |

A current index adds no key at all. Two further effects: a schema-stale reply has its "definitive empty result" claim withdrawn (`_withdraw_definitive`, `tools_query.py:257`), and a routed reply is annotated only for the repository it actually read.

**What the caller does.** Most of the work is done by the server, not the agent:

```
query tool called
  └─ _answering_with_refresh   (server.py:519, wraps each query tool)
       └─ _auto_refresh        (server.py:1242)
            ├─ data stale AND matches_source? → _refresh_stale
            │     bounded lock wait, re-check inside lock,
            │     skip_if_fresh, never raises, failures logged
            ├─ db file absent?               → background first build
            └─ otherwise                     → answer as-is
       └─ run the query, then attach staleness notices
```

`_data_stale` (`server.py:1209`) refuses the refresh for the `schema` and `code` axes. A `code`-stale process rebuilding would run old pipeline logic and re-stamp the index, so the server declines to attempt it. For those two axes the agent has to act: restart the client, or force a rebuild in the older-index case.

**Caveats.** I read this from the index's dossiers and function bodies; I did not run `status` or exercise a stale index. The dossier for `clew/mcp_server/freshness.py` as a file reported it as not indexed, though `search` lists it, so I relied on the function-level dossiers for `notices` and the axis builders.