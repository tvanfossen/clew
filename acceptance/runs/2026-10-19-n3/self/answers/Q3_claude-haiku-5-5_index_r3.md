The index detects staleness on three separate axes, and since the index now refreshes itself, the agent mostly sees the result of a refresh rather than having to act on a warning.

**How the tool knows**

`db_status` (`clew/mcp_server/state.py`) computes `stale` as true when any of three things holds:
- the database doesn't exist,
- the build stamp differs from the server's expected build version,
- or `source_changed_files > 0`, which `_source_drift` measures against the repo.

`freshness.py` then turns those measurements into three named axes, each with its own remedy:

| Axis | Condition | Remedy | Refreshable? |
|---|---|---|---|
| `data` | Indexed sources have changed since the build | `index(action='refresh')` | Yes |
| `schema` | Index stamped by a newer build than this server (`build_version > expected`) | None: a rebuild re-stamps the same version. Restart the MCP client | No |
| `schema` | Index older than server | `index(action='refresh', force=True)` | Yes |
| `code` | The running server process loaded clew before the package source changed | Restart the MCP client. A rebuild can't fix it | No |

`notices()` returns only the active axes, in data → schema → code order, and returns an empty list when the index is current, so a current index adds no noise to replies.

**What the tool tells the caller**

- Every query reply carries a `staleness` block only when an axis is active (`staleness_notices` in `server.py`). It is absent when current.
- When the schema axis is stale, `_withdraw_definitive` rewrites an empty result's "definitive, do not retry" note, because a missing layer may be an unrebuilt index rather than a real absence.
- `status` is the full diagnosis, but the docstrings say a session shouldn't open with it, since staleness already shows up on the first reply.

**What the caller does**

Queries no longer leave the fix to the caller. The sequence is:

1. `answering` (in `_answering_with_refresh`) calls `_auto_refresh` before the query runs.
2. `_auto_refresh` resolves the same database the query will read (`target` plus `sub_index`), then either refreshes it or builds it if it is absent.
3. `_data_stale` gates the refresh. It returns false unless the process matches the source tree and the only active axis is `data`. This stops a stale server from running an old build that could drop layers and re-stamp the index.
4. `_refresh_stale` takes the per-repo build lock with a bounded wait, re-checks staleness inside the lock so concurrent sessions deduplicate to one build, and logs failures. It never raises.
5. If the refresh fails or the lock wait times out, the query answers from the existing index and the reply still carries its staleness notice.

The agent only needs to act on a `schema` or `code` notice, and then by restarting the client. For a `data` notice it can call `index(action='refresh')` explicitly, but the query path usually makes that unnecessary.

**Caveats**

- I read these through the clew index (bodies and docstrings), not by opening the source files. `_staleness` was flagged `anchor_mismatch: true`, so its body may not match the current file.
- I did not check the tests, but the test names (e.g., `test_a_query_refreshes_only_when_the_data_axis_is_stale`, `test_build_or_refresh_refuses_when_the_process_predates_its_source`) match the behaviour described.