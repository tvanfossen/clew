**Short answer:** the index checks its own currency on every query and attaches a `staleness` block to any reply it would otherwise mislead on. The caller reads that block and, for most axes, runs `index(action='refresh')`. The exception is the code axis, where only a client restart helps.

**How it knows.** Three axes are measured separately (REQ-DDB-MCP-004):

| Axis | Meaning | Fix |
|---|---|---|
| `data` | The database is older than the source tree. | `index(action='refresh')` |
| `schema` | The stamped build version differs from the one this server expects. | Rebuilding re-stamps the same version, so it does not help when the index is newer. |
| `code` | This server process is older than the working tree. | Restart the client. A build through the stale process is refused. |

The data check is not just a version compare. A test (`test_db_status_detects_source_drift`) records that a version-only check let a database built before many source edits report `stale: false`, and `build_or_refresh` then refused to rebuild. Source drift is therefore detected from mtimes.

**What it tells the caller.**
- `staleness_notices` (`clew/mcp_server/server.py:1548`) returns a list of `{axis, message}`. It is empty when the index is current, so a healthy index adds no noise.
- The notices ride in the payload of every query reply, including misses. The point is that a caller holding a fresh-looking answer would not think to call `status` to check.
- A routed reply is annotated with the staleness of the repository it actually read, not the default one.
- The annotation never raises. If staleness cannot be measured, the reply goes out unannotated.
- `status` reports `stale` unconditionally, but its interpretation is omitted when there is nothing to interpret.

**What the caller does.**
1. Read the `axis`. `data` staleness alone keeps definitive empty answers (`test_data_staleness_alone_keeps_the_definitive_claim`). `schema` staleness withdraws them.
2. For `data`, call `index(action='refresh')`. If the index is current, this is a cheap skip. The reply reports a measured `duration_ms` for the call, which lets the caller state what the correction cost.
3. For `code`, restart the client. A refresh is refused until then, and `force` cannot override the refusal.
4. Concurrent refreshes of one target produce a single build, because the freshness check runs inside the per-target lock.

**One observation from this session.** My dossier replies flagged `anchor_mismatch: true` on `_staleness` and `build_or_refresh`. The docs define that as "the file changed since the build." I did not see a top-level `staleness` block on those replies. Either the per-symbol flag is a separate signal from the reply-level block, or the two disagree. I could not settle which from the index alone. Running `index(action='status')` would show the axes directly.