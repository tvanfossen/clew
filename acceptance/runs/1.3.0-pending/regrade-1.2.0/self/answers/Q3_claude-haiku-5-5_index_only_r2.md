The index knows it is stale by measuring three separate axes. It tells the caller on the reply itself, and the caller's action depends on which axis is stale. Everything below is from the index's own documentation and function bodies; I did not run `index(action='status')`.

**How it knows**

`db_status` measures freshness. `freshness.py` turns those raw fields into three named axes, each cleared by a different action:

| Axis | Meaning | Detected by | Cleared by |
|---|---|---|---|
| `data` | Database is older than the source | `db_status` reports it as `source_changed_files`. Source drift is caught by mtimes, not just the version stamp (see `test_db_status_detects_source_drift`). | A rebuild |
| `code` | The running server process loaded clew at launch and the package source has changed since | `code_identity()` compares the process fingerprint with the on-disk source fingerprint | Restarting the MCP client only |
| `schema` | `build_version` differs from `expected_build_version` | Version integers in the payload | Nothing the consumer can do when the index is newer than the server. A rebuild re-stamps the same newer version. |

The `code` axis is the subtle one. Queries open the database per call, so data reads are live. The stale part is the process's logic and module constants. The docs say a stale process reads current data but writes with dead logic. That is why the code axis is the one that can mislead.

**What it tells the caller**

- Every query reply carries a `staleness` block only when something is stale. `staleness_notices()` returns a list of `{axis, message}` and is empty when the index is current or unmeasurable. The block is attached by `_staleness`, which is measured against the real payload. If the full prose does not fit, it is compacted, then reduced to a minimal form. It is never silently dropped.
- For a routed query, the notice describes the repository that was actually read, never the default one.
- Separately, `status` always reports `stale`, but the interpretation is only added when there is something to interpret.
- Definitive claims are scoped. Per the tests, data staleness alone does not withdraw an empty result's "definitive" claim, but schema staleness does.
- Write paths call `stale_code_refusal()`. If the process predates its source, the write is refused. The `force` flag does not override this.

**What the caller does**

1. **`data`:** Usually nothing. `_data_stale` decides whether an auto-refresh is safe and needed. If the process matches its source, a query triggers `_refresh_stale`, which rebuilds under the per-repo build lock with a bounded wait. If the lock wait times out, the query answers from the existing index and keeps the notice. A manual `index(action='refresh')` also works.
2. **`code`:** Restart the MCP client so it loads the current code, then call `index(action='refresh', force=True)`. Reads can continue meanwhile, but writes are refused.
3. **`schema`:** A rebuild through this process will not clear it. The notice means the index was built by a newer clew than the one answering. The caller should use a matching clew version rather than trust an empty or definitive-looking result.

The design rule behind all of this is that a rebuild through a stale process is never attempted, because it can drop layers and then report healthy. The refusal is cheap, since one client reconnect fixes it.

Two dossier bodies (`_staleness` and `_staleness_within_budget`) came back with `anchor_mismatch: true`, so their line numbers may not match the current file. The behaviour described above is from their docstrings and the freshness module docs, and I did not verify it against the source.