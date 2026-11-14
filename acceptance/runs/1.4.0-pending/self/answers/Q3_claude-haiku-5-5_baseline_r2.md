A clew index is judged stale on three independent axes. The tool reports them as a `staleness` list on every reply, and the caller usually does not have to act, because query tools refresh the data axis automatically. The one axis a rebuild cannot fix needs a client restart.

**How it knows**

| Axis | Measured by | Cleared by |
|---|---|---|
| `data`: sources changed since the build | `_source_drift` (`clew/mcp_server/state.py:823`) stats each indexed file and compares its mtime with the database's mtime | rebuild |
| `schema`: the index was built by a different pipeline version | `build_version` in `build_meta` vs `CLEW_BUILD_VERSION` (`clew/signature.py`) | rebuild if the index is older; restart the client if it is newer |
| `code`: the running server imported older clew code than is on disk | `source_fingerprint` (`clew/mcp_server/freshness.py:112`) hashes relative path and content of every package `.py`, compared against a fingerprint taken at import | restart the client only |

`db_status` sets `stale` from the first two only (`state.py:1197`), so a `code` mismatch does not show up in `stale`.

**What it tells the caller**

`freshness.notices()` (`freshness.py:573`) returns a list of `{axis, message}` and is empty when everything is current. `staleness_notices()` (`server.py:1548`) attaches that list to query replies, so when the index is current the field is simply absent. The messages name the fix:
- `data`: "call `index(action='refresh')`", with the measured cost of the last refresh from `build_meta`.
- `schema`, older index: `index(action='refresh', force=True)`. Newer index: restart the client, because a rebuild re-stamps the same newer version and cannot clear it.
- `code`: restart the client. Reads are still accurate because queries reopen the database per call, but writes are refused, since an old process rebuilding would drop layers.

**What the caller does**

- **Query tools, automatically.** Every query is wrapped by `_answering_with_refresh` (`server.py:519`), which calls `_auto_refresh`. It refreshes only when the `data` axis is stale and `matches_source` is true (`_data_stale`, `server.py:1209`). The refresh takes the per-repo build lock with a bounded wait, re-checks staleness inside the lock so concurrent queries deduplicate to one build, and builds with `skip_if_fresh=True`. A failed or timed-out refresh still answers from the stale index, with the notice attached.
- **Absent index.** A first build starts in the background, but only if `_first_build_refusal` finds a git work tree or a registered repo, and the process is not stale (`server.py:1368`).
- **Background.** `keep_current` runs `refresh_touched` on a timer (`server.py:1538`).
- **Explicit.** `build_or_refresh` (`server.py:2189`) refuses with `stale_code_refusal` when the code axis fires. `force` does not get past that refusal.

**Gaps I noticed (not run, read from code)**

- `_source_drift` stats only paths already in the `path` table. A source file added since the build is never counted, so a new file does not mark the index stale.
- Deleted files are skipped silently (`state.py:866`) on the assumption the rebuild will notice.
- Mtime is the data signal, so a `git checkout` that rewrites identical content still marks the index stale. That costs a rebuild but never a wrong answer.
- Config changes (Doxyfile, scope) are only caught through mtime of indexed paths, or through a `build_version` bump. I did not verify the config case.