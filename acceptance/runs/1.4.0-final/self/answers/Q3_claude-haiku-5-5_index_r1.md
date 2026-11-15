**Short answer:** the index compares itself against the source tree and the running server process, reports the result as a `staleness` list on every reply, and the caller (or the server) acts on it per axis. Data staleness is refreshed automatically, schema staleness is not fixable by a rebuild, and code staleness blocks writes until the client restarts.

**How it knows**

`db_status` (`clew/mcp_server/state.py`) measures the database. `code_identity` (`clew/mcp_server/freshness.py`) measures the process. Three axes come out of that:

| Axis | Condition | Meaning |
|---|---|---|
| `data` | `source_changed_files > 0` | Sources changed since the db was built |
| `schema` | `build_version` ≠ `expected_build_version` (`CLEW_BUILD_VERSION` in `clew/signature.py`) | Stamped by a different pipeline build. If the index is *newer*, no rebuild clears it |
| `code` | `matches_source` false (process fingerprint ≠ on-disk source fingerprint) | The server loaded old logic at launch and the package has changed since |

Reads are live because each query opens the db, so data is current. The process's logic is what is stale. Writes are the hazard, because a stale process rebuilding would stamp the index with old logic. The module docstring records a real incident where a stale build-30 process rebuilt a build-32 index, dropped the `external` stage, and then reported `stale: false`.

**What it tells the caller**

- Every query reply carries `staleness`: a list of `{axis, message}`, built by `notices()`. The list is empty when the tool is current, and the key is absent, so a current index adds no noise.
- Each message names the action that clears it. The messages are sized to the response budget in three tiers: full prose, compact, then minimal.
- `index(action='status')` and `list_targets` expose the same facts as `stale`, `build_version`, `expected_build_version`, and `source_changed_files`.

**What the caller does**

1. **data:** the server refreshes automatically. `answering()` runs `_auto_refresh`, which calls `_refresh_stale` and `_data_stale`. The rebuild uses `skip_if_fresh=True` under a bounded build-lock wait. Failures are logged and the reply still goes out with its notice. A caller can also run `index(action='refresh')`.
2. **schema:** nothing the caller can do through this process clears it. Auto-refresh skips it, because a rebuild re-stamps the same newer version.
3. **code:** `stale_code_refusal()` returns a refusal, and `build_or_refresh` checks it before touching an index. Auto-refresh never attempts a build while `matches_source` is false. `force=True` does not bypass the refusal. The remedy is to restart the MCP client so it loads current code, then run `index(action='refresh', force=True)`.

**Caveats**

- Some bodies came back flagged `anchor_mismatch` (`notices`, `QueryTools._staleness`, `_staleness_within_budget`), so the line numbers may be off from the current source. I cited functions by name and did not re-read those bodies.
- I did not run anything against this index. This answer comes from the dossier bodies and the test names that cover them.