# Q7 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "*.py" | head -20
- **got:** ~/ddb-targets/self/acceptance/bench/rescore_audit.py ~/ddb-targets/self/acceptance/bench/fallback_audit.py ~/ddb-targets/self/acceptance/bench/arm_headroom.py ~/ddb-targets/self/acceptance/bench/bench_arms.py ~/ddb-targe…

### 2. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "__main__.py" -o -name "main.py" | head -10
- **got:** ~/ddb-targets/self/doxyguard_db/mcp_server/__main__.py ~/ddb-targets/self/doxyguard_db/__main__.py

### 3. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/__main__.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Module entry point: `python -m doxyguard_db`. 3	 4	Defers to `cli.main`. Exists so a caller can run the package via 5	`python -m doxyguard_db ...` without needing a wrapper script. 6…

### 4. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db
- **got ⚠ error:** EISDIR: illegal operation on a directory, read '~/ddb-targets/self/doxyguard_db'

### 5. `Bash`
- **asked:** command=ls -la ~/ddb-targets/self/doxyguard_db/ | head -30
- **got:** total 1588 drwxrwxr-x 5 tvanfossen tvanfossen   4096 Aug 16 10:30 . drwxrwxr-x 9 tvanfossen tvanfossen   4096 Aug 16 10:30 .. -rw-rw-r-- 1 tvanfossen tvanfossen  84806 Aug 16 10:30 ast_symbols.py -rw-rw-r-- 1 tvanfossen …

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""argparse + pipeline glue for `python -m doxyguard_db`. 3	 4	The pipeline runs in fixed order: 5	  1. doxygen → SQLite + XML 6	  2. copy_database to the user-specified --output path 7…

### 7. `Bash`
- **asked:** command=grep -n "incremental\|cache\|skip\|reuse" ~/ddb-targets/self/doxyguard_db/cli.py | head -30
- **got:** 133:from .indexcache import IndexCache 319:##   * `index_cache` / `no_index_cache` — the sidecar path is DERIVED from `--output`, and 320:##     `--rebuild` is the operator-facing "do not trust the cache" verb. See 321:#…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/indexcache.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Sidecar index cache store making rebuilds incremental. 3	 4	File identity hashing and tree enumeration live in the sibling `treescan` 5	module; this one owns the sidecar SQLite datab…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/indexcache.py
- **got:** 150	            "index cache: doxygen_cache shape %s → %s — rebuilding that table", 151	            sorted(columns), 152	            sorted(_DOXYGEN_CACHE_COLUMNS), 153	        ) 154	        self.conn.execute("DROP TABLE…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/indexcache.py
- **got:** 380	 381	    ## @brief Look up a previously generated doxygen SQLite output. 382	    ## @return Path to the cached doxygen db when it still holds THIS key's output, else None. 383	    ## @version 3 384	    ## @req REQ-DD…

### 11. `Bash`
- **asked:** command=grep -rn "STAGE_VERSION\|stage_version" ~/ddb-targets/self/doxyguard_db/ --include="*.py" | head -40
- **got:** ~/ddb-targets/self/doxyguard_db/ast_symbols.py:968:## changing the shape again — and `stage_version` is bumped alongside, which is what ~/ddb-targets/self/doxyguard_db/ast_symbols.py:1012:    stage_version = 6 ~/ddb-targ…

### 12. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1200	## @version 7 1201	## @dg_internal 1202	def _doxygen_stage( 1203	    doxyfile: Path, 1204	    repo_root: Path, 1205	    args: argparse.Namespace, 1206	    cache: IndexCache | None, 1207	    preprocessor: Preprocesso…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1270	## @req REQ-DDB-CONFIG-001 1271	def _build_stages( 1272	    output: Path, 1273	    doxyfile: Path, 1274	    args: argparse.Namespace, 1275	    cache: IndexCache | None = None, 1276	    timer: StageTimer | None = Non…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/signature.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Build-version signature stamped into every built docs.db. 3	 4	The pipeline owns the constant and the stamping (a `build_meta` row written 5	as the LAST stage, so a partial build nev…

### 15. `Bash`
- **asked:** command=grep "DOXYGUARD_DB_BUILD_VERSION\|^[0-9]*:" ~/ddb-targets/self/doxyguard_db/signature.py | head -50
- **got:** DOXYGUARD_DB_BUILD_VERSION = 50 ## @param version Version to stamp (defaults to DOXYGUARD_DB_BUILD_VERSION).     version: int = DOXYGUARD_DB_BUILD_VERSION,

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/harvest.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Per-file tree-sitter parse plumbing + the cached harvest driver. 3	 4	TEN pipeline stages walk EVERY indexed C/C++ file's AST (kconfig gates, 5	recovered symbols, call edges Layer 3,…

### 17. `Bash`
- **asked:** command=grep -n "extra_key\|manifest_key" ~/ddb-targets/self/doxyguard_db/buildoptions.py | head -40
- **got:** 635:    inline form adds a route, not a format, and `treescan.manifest_key` hashes a mapping

### 18. `Bash`
- **asked:** command=grep -rn "manifest_key\|extra_key" ~/ddb-targets/self/doxyguard_db/ --include="*.py" | grep "def manifest_key\|extra_key\s*=" | head -40
- **got:** ~/ddb-targets/self/doxyguard_db/harvest.py:277:        self.extra_key = extra_key ~/ddb-targets/self/doxyguard_db/treescan.py:112:def manifest_key(source: Path | dict | None) -> str: ~/ddb-targets/self/doxyguard_db/index…

### 19. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/treescan.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""File-identity hashing and indexed-tree enumeration for incremental builds. 3	 4	Split from `indexcache` by responsibility: this module answers "what files does 5	this build read, and…

### 20. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/harvest.py
- **got:** 250	        current = current.parent 251	    return current 252	 253	 254	## @brief Base class for a cacheable per-file AST extraction stage. 255	## @version 1 256	class Harvester: 257	    """One per-file AST extraction …

### 21. `Bash`
- **asked:** command=grep -n "mark_reachability\|thread\|boundary\|requirements\|CROSS-FILE" ~/ddb-targets/self/doxyguard_db/cli.py | head -50
- **got:** 39:     interface→implementor edges + interface-boundary termini + fnptr dispatch 42:     the thread-membership and reachability BFS below can flow across the seam. 43: 10. extract_threads (R1: threads + thread_membershi…

**Reasoning.** ## ANSWER

Re-running on barely-changed repositories avoids repeating work through **three-tier caching**: doxygen tree-hash skip, per-file AST extraction caching, and uncached cross-file graph computation.

---

### How Incremental Execution is Achieved

**Doxygen Stage (Tree-Hash Skip):** `cli.py:1210-1261` — doxygen has no incremental mode, so the pipeline hashes every file in the indexed tree plus the exact Doxyfile text and runs doxygen only when the tree hash changes. The cached doxygen SQLite output is reused when that hash matches.

**Per-File AST Extraction (10 Stages):** `harvest.py:

---

## Final answer as submitted

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
