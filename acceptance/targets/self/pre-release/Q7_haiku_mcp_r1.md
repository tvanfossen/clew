# Q7 — mcp — haiku — run 1

## ANSWER

Incremental rebuilds are achieved through a **sidecar SQLite cache file** (`<output>.idxcache` by default) that tracks what work has been done and whether it can be reused.

### How Incrementality Works

**Three cached tables** hold the state:

1. **`source_files`** — Per-file identity: `(path, size_bytes, mtime_ns, content_sha)`. The **content sha256 is the authority**; size+mtime is only a prefilter (skip re-hashing when both match). A `touch` with no edit stays a cache hit. A branch checkout that restores identical bytes stays a hit.

2. **`extract_cache`** — Content-addressed per-file AST harvest payloads, keyed by `(content_sha, stage, stage_version, extra_key)`. Payloads are rowid-FREE (record source line numbers + identifier text, not doxygen rowids) because doxygen renumbers on every run. Rowid resolution happens on every build against the freshly generated memberdef table.

3. **`doxygen_cache`** — Maps `tree_sha` (hash of the whole tree, Doxyfile content, and forced flags) to the doxygen SQLite output that tree produced. An unchanged tree skips the doxygen run entirely. The cache is verified by content (`output_sha`), not existence, because all keys in the table name the same output path which successive builds overwrite.

### Where State is Kept and Why

**Sidecar database file** (`<output>.idxcache` by default), kept separate from `docs.db` because docs.db is **rebuilt from scratch on every run** (doxygen → copy → augment → `os.replace`). The incrementality state cannot live inside a file that gets demolished and rebuilt; a sidecar is pure cache and safe to discard. `doxyguard_db/indexcache.py:1-34`, `doxyguard_db/indexcache.py:89-104`

### Everything That Can Make Previously Done Work No Longer Usable

1. **Build-version bump** (`DOXYGUARD_DB_BUILD_VERSION` in `doxyguard_db/signature.py`): Wipes all three cache tables. Logic moved; drop everything. `doxyguard_db/indexcache.py:161-189`

2. **Per-stage version bump** (`stage_version` constant in each stage class): Invalidates exactly that stage only; a single combined key would be all-or-nothing. `doxyguard_db/harvest.py:18-24`, `doxyguard_db/harvest.py:259-271`

3. **Manifest content change** (`--thread-patterns`, `--shared-key-patterns`, `--mqtt-dispatch`, `--data-model`, `--guard-config`, or their `.doxyguard-db.yaml` equivalents): The manifest's sha256 folds into `extra_key`, which is part of the cache key. `doxyguard_db/treescan.py:107-131`

4. **File content change**: Content sha differs from stored identity. `doxyguard_db/indexcache.py:224-250`

5. **File deletion**: Removed files are dropped from `source_files` at commit, so no longer hit. `doxyguard_db/indexcache.py:507-526`

6. **File mtime or size change**: Triggers re-hashing (prefilter missed), which may reveal content changed. `doxyguard_db/indexcache.py:206-218`

7. **Doxygen output overwrite**: Another build's `tree_sha` can point to the same output file path, overwriting it. Hit is conditional on recorded digest (`output_sha`) matching the file now at that path. `doxyguard_db/indexcache.py:385-435` (#399)

8. **Schema mismatch in `doxygen_cache` table**: Column shape change (e.g., older sidecar without `output_sha` column). Table is dropped and recreated rather than migrated, forcing a fresh doxygen run. `doxyguard_db/indexcache.py:129-156`

9. **`--rebuild` flag**: Disables reads from prior runs (all external lookups MISS) but exempts payloads this run computed, so one forced build re-warms the cache. `doxyguard_db/indexcache.py:95-100`, `doxyguard_db/indexcache.py:278-283`

### What is NOT Made Incremental

**Cross-file stages** are never cached: `doxyguard_db/harvest.py:32-34`
- Reachability (depends on whole assembled graph)
- Thread membership (depends on whole assembled graph)
- Boundary annotation (thread-boundary flags on edges)
- Requirements linking (depends on whole graph)

These "are cheap" — they run once per build over the whole database after per-file extraction is complete, not per-file.

**docs.db itself** — The entire database is rebuilt from scratch on every run: doxygen output is copied in, then augmented with all layers, then atomically replaced (`os.replace`). Only the doxygen SQLite output itself (one piece of input) is cached.

## Gaps

No gaps. The index answered the full causal chain: sidecar file location, cache tables, invalidation rules, per-stage granularity, and what remains always-fresh.
