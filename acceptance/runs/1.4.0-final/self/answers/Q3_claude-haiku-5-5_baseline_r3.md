A clew index can go stale on three independent axes. The tool detects each one, reports it as a `staleness` block on every MCP reply, and the query path acts on the data axis automatically. The other two need a client restart, which no tool call can do.

**How it knows** (`clew/mcp_server/state.py` `db_status`, `clew/mcp_server/freshness.py`)

| Axis | Test | Cleared by |
|---|---|---|
| `data` | Any indexed source file has mtime newer than the db, or the stamped build version differs. | Rebuild (`index(action='refresh')`) |
| `schema` | `build_version` vs. `CLEW_BUILD_VERSION`. Direction matters. | Rebuild if the index is older. If the index is newer, only a client restart helps. |
| `code` | The running process's source fingerprint (taken at import) vs. a sha256 over every `.py` under the package, by relative path and content. | Only restarting the client |

Details that matter:
- Data drift uses mtime, but only for paths already in the `path` table. A file that was deleted is skipped, and a brand-new file that was never indexed is not seen. Mtimes more than 300 s in the future are ignored so a skewed clock cannot keep an index stale forever.
- The code fingerprint hashes content, not mtime, because a `git checkout` changes mtime without changing content. An empty fingerprint means "cannot tell", and that is treated as matching.

**What the caller is told**

- `db_status` puts a `staleness` list on the status reply. Each entry is `{axis, message}`, and the key is absent when the index is current.
- Every query reply carries the same block when stale. The data notice names `index(action='refresh')` and quotes the measured cost of the last refresh.
- The schema and code notices say a rebuild cannot clear them, and tell the caller to restart the MCP client.
- A write refused for the code axis returns `REFUSED: …` and writes nothing.

**What the caller does**

1. **Query tools, automatically.** Before answering, `_auto_refresh` checks the data axis. It refreshes only if the data axis is stale and the code axis matches, since a build from a stale process would drop layers. The refresh takes the per-repo build lock with a bounded wait and re-checks staleness inside the lock, so concurrent queries produce one build. An absent index gets a background first build.
2. **Failure degrades, never errors.** If the refresh fails or times out, the query answers from the existing index and the reply still carries the notice.
3. **Background loop.** `keep_current` calls `refresh_touched` on an interval. The comment in `state.py` says 15 s; I did not confirm that from the call site.
4. **Explicit refresh.** `build_or_refresh` refuses on the code axis before taking the lock. `force=True` does not get past that refusal. For a stale schema it says to rebuild with `force=True`, or to restart the client when the index is newer.
5. **The consuming agent.** It reads the `staleness` block and acts on the axis named in the message. This is the only step that depends on the agent, and it is the one the auto-refresh was added to avoid relying on.

**Limits I noticed**

- New source files added after the build are not detected, because only indexed paths are stat'd.
- A file restored with an old mtime (an archive extract that preserves timestamps, for example) is missed by the data axis.
- I read the MCP server path only. I did not check whether the CLI `status` output reports the same notices.