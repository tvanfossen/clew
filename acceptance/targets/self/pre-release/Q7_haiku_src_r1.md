# Q7 — src — haiku — run 1

## ANSWER

Re-running on barely-changed repositories avoids repeating work through **three-tier caching**: doxygen tree-hash skip, per-file AST extraction caching, and uncached cross-file graph computation.

---

### How Incremental Execution is Achieved

**Doxygen Stage (Tree-Hash Skip):** `cli.py:1210-1261` — doxygen has no incremental mode, so the pipeline hashes every file in the indexed tree plus the exact Doxyfile text and runs doxygen only when the tree hash changes. The cached doxygen SQLite output is reused when that hash matches.

**Per-File AST Extraction (10 Stages):** `harvest.py:1-38` — ten stages walk every indexed C/C++/Python file's AST (kconfig gates, recovered symbols, call edges, callbacks, locks, dispatch, threads, shared keys, MQTT, Python guards). Each stage's `harvest()` method previously drove its own full-tree parse pass, redundantly re-parsing each file ten times. `gh#358` unified this: one shared parse produces `(content_sha, stage, stage_version, extra_key)` cache rows that each stage reads back. `cli.py:1346-1359` documents the single `warm_harvest_plan` that parses each file once and warms every stage's cache row before the stages run.

---

### Where State is Kept and Why

**Location:** A sidecar SQLite database at `<output>.idxcache` (derived from `--index-cache` or `--output` path). `indexcache.py:1-34` documents it as independent from `docs.db` because `docs.db` is rebuilt from scratch on every run — incrementality state cannot live inside it.

**Three Tables:**

1. `source_files` — repo-relative path → (size_bytes, mtime_ns, content_sha). `mtime+size` is a prefilter; `content_sha` is the authority. `indexcache.py:194-200` loads the previous scan; `indexcache.py:220-250` classifies the current scan into unchanged/modified/added/removed.

2. `extract_cache` — `(content_sha, stage, stage_version, extra_key)` → payload. Payloads are rowid-FREE (recording source line numbers + identifier text, not doxygen rowids, which are unstable across runs). `harvest.py:279-289` documents this as the base class contract.

3. `doxygen_cache` — `tree_sha` → `(db_path, output_sha, created_at)`. Stores the HASH of the doxygen output, not just the path, because multiple configurations can point at the same output file and overwrite it. `indexcache.py:381-435` details the false-hit fix (#399) — comparing the recorded digest against the file's current digest.

---

### What Makes Previously Done Work No Longer Usable

**1. `DOXYGUARD_DB_BUILD_VERSION` Bump** (currently 50, `signature.py:368-465`) — Any version bump wipes the entire cache: `indexcache.py:161-188` deletes all three tables. Examples from the 300+ comments in `signature.py`:
- Version 29–34: index scope changes (INPUT roots, EXCLUDE, FILE_PATTERNS, external-tree detection)
- Version 31: C++ RAII lock-pattern matching rule tightened; old indices carry fabricated lock rows
- Version 32–33: nested git trees now indexed instead of excluded

**2. Per-Stage `stage_version` Bump** — Each stage (e.g., `call_edges.stage_version = 4`, `threads.stage_version = 4`, `kconfig_gates.stage_version = 4`) carries its own version. Bumping one stage invalidates only that stage's cache entries, not all ten. `harvest.py:15-23` explains why the key is NOT merged: a combined key would be all-or-nothing (every edit forces a full re-parse) or lossy (a changed component the combine omitted would serve stale logic).

**3. File Content Changes** — `indexcache.py:206-218` re-hashes files when the prefilter (size+mtime) misses. Content SHA decides; mtime alone cannot catch `git checkout` or `touch` without edits. `indexcache.py:224-250` buckets the scan into changed/unchanged/added/removed; modified files are re-parsed.

**4. File Additions/Removals** — `indexcache.py:232-246` detects added files (not in previous scan). `indexcache.py:247-249` detects removed files (in previous scan but not in current files dict). `indexcache.py:517-525` replaces `source_files` on commit, so removed files stop hitting the cache.

**5. Manifest Changes** — Each stage that reads a manifest (thread-patterns, shared-key-patterns, dispatch, mqtt-dispatch, data-model) folds the manifest's content hash into `extra_key`. `treescan.py:112-131` — `manifest_key` hashes the manifest's CONTENT (whether it arrives as a file or as a `.doxyguard-db.yaml` section). A changed declaration changes the key, invalidating that stage's cache entries. `harvest.py:276-277` — each `Harvester` instance carries the `extra_key`.

**6. Doxygen Output Verification** — `indexcache.py:414-434` — `doxygen_get` looks up the cached output by tree hash, then **verifies it by content hash**. If another configuration has overwritten the output file, the recorded SHA no longer matches the file's current SHA, and the lookup returns `None` (cache MISS). This prevents false hits when multiple `tree_sha` keys point at the same overwritten file.

**7. Output Failure to Hash** — `indexcache.py:451-459` — if the doxygen output cannot be hashed (unreadable file), it is not cached. On the next run, a later unreadable read would compare `"" == ""` and HIT — a false hit. The empty string is explicitly rejected.

**8. Cache Path Mismatch** — `cli.py:319-321` documents that the sidecar is keyed to the cache/output directory. Two builds sharing a cache must share the same `--index-cache`/`--output` path; different cache directories lose the skip. `--rebuild` disables reads of prior entries but still refreshes the cache `indexcache.py:94-100`, so the next build is incremental again.

---

### What is NOT Made Incremental

**Doxygen Run Itself** — `cli.py:1210` states "doxygen has no incremental mode." Only the SKIP is incremental (tree-hash reuse), not the run.

**All Cross-File Stages** — `cli.py:1282-1284` explicitly documents: "every CROSS-FILE stage below — reachability, thread membership, boundary annotation, requirements — is always recomputed, because they depend on the whole assembled graph." These are:
- `mark_reachability` `cli.py:1617` — BFS from entry-point seeds, depends on the entire call-edge graph
- `extract_threads` `cli.py:1501` — thread membership, depends on all member and call edges
- `annotate_thread_boundaries` `cli.py:1576` — crosses_thread / to_thread_id annotation on shared-key edges
- `ingest_requirements_yaml` `cli.py:1599` — requirement ingestion and tracing
- `import_req_edges` — @req tag traceability
- `import_req_test_edges` — test function coverage tracing

**Downstream Per-File Stages that Feed Cross-File Computation** — `cli.py:1280-1284` notes that `cache` makes "per-file AST stages incremental." But a per-file stage whose output feeds a cross-file stage (e.g., call edges feed reachability, thread extraction feeds membership) still runs its per-file extraction; it is only the storage/lookup that is cached.

**Non-AST Pipeline Stages** — These are always recomputed:
- `copy_database` `cli.py:1315` — temp copy of doxygen output
- `sanitize_doxygen_text` `cli.py:1319` — UTF-8 repair
- `enrich_database` `cli.py:1327` — optional enrichment
- `fix_doxygen_paths` `cli.py:1330` — STRIP_FROM_PATH undo
- `repair_attribute_named_functions` `cli.py:1332` — attribute function merges/renames
- `ingest_supplementary_docs` `cli.py:1334` — README + docs/*.md ingestion
- `import_kconfig` `cli.py:1344` — Kconfig variant space ingestion

`cli.py:1336-1339` notes that `ingest_supplementary_docs` DROPs and recreates the `supplementary_docs` table on every build; running kconfig ingestion above it would insert chunks that get deleted, with no error.

---

## Gaps

None identified. The code clearly documents the cache mechanism, invalidation rules, and cross-file stage exclusion from incrementality. The manifest-key mechanism for stage-specific invalidation on declaration changes is fully traceable from `cli.py:1363-1375` through `treescan.manifest_key` and each stage's `extra_key` field.
