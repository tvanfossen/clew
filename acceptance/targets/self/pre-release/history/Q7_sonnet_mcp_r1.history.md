# Q7 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"doxyguard_db/indexcache.py","kind":"file","file":"doxyguard_db/indexcache.py","brief":"Sidecar index cache store making rebuilds incremental. File identity hashing…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"prose matches","count":3,"results":[{"file_path":"doxyguard_db/indexcache.py","heading":"doxyguard_db/indexcache.py — file-level documentation","snippet":"doxyguard_db/indexcache.py Sidecar index >>cache<< store…

### 3. `mcp__doxyguard-db__dossier`
- **asked:** kind=file
- **got ⚠ error:** Error executing tool dossier: Subject kind 'file' names no dossier subject: a file has no dossier — its documentation is `search(corpus='prose')`.

### 4. `mcp__doxyguard-db__search`
- **asked:** text
### 5. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"tests/test_self_edges.py","kind":"file","file":"tests/test_self_edges.py","brief":"The self-edge guard (#61): genuine recursion kept, fabrications dropped. A `call…

- **got:** {"kind":"matching symbols","count":3,"results":[{"name":"doxyguard_db::treescan::FileIdentity","kind":"class","file":"doxyguard_db/treescan.py","brief":"One file's cheap identity (size + mtime) plus its authoritative sha…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"doxyguard_db::treescan::FileIdentity","subject_kind":"class","name":"doxyguard_db::treescan::FileIdentity","kind":"class","file":"doxyguard_db/treescan.py","line":31,"brief":"One file's cheap identity (size +…

### 7. `mcp__doxyguard-db__search`
- **asked:** corpus, text
### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/treescan.py
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"treescan.py functions","note":"No indexed file matches 'treescan.py functions'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data…

- **got:** 1	# SPDX-License-Identifier: MIT 2	"""File-identity hashing and indexed-tree enumeration for incremental builds. 3	 4	Split from `indexcache` by responsibility: this module answers "what files does 5	this build read, and…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/indexcache.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Sidecar index cache store making rebuilds incremental. 3	 4	File identity hashing and tree enumeration live in the sibling `treescan` 5	module; this one owns the sidecar SQLite datab…

### 10. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"doxyguard_db/indexcache.py","heading":"doxyguard_db/indexcache.py — file-level documentation","snippet":"…>>docs<<.>>db<< is rebuilt from scratch on every run (…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
### 12. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""argparse + pipeline glue for `python -m doxyguard_db`. 3	 4	The pipeline runs in fixed order: 5	  1. doxygen → SQLite + XML 6	  2. copy_database to the user-specified --output path 7…

- **got:** {"kind":"prose matches","count":1,"results":[{"file_path":"tests/test_enrichment.py","heading":"tests/test_enrichment.py — file-level documentation","snippet":"…field defaults, and the idempotent >>replace<<->>on<<->>rer…

**Reasoning.** ## How re-runs avoid repeating work

The pipeline caches at two points, both guarded by a **sidecar SQLite file** (`<output>.idxcache`) that sits alongside — but separate from — `docs.db`. It has to be separate because `docs.db` itself is thrown away and rebuilt from scratch on *every* run: `doxygen → copy → augment → os.replace` (`doxyguard_db/indexcache.py:7`). Since the final output is never mutated incrementally, the state that makes re-runs cheap can't live inside it — it lives in this sidecar, in three tables (`doxyguard_db/indexcache.py:9-24`):

- **`source_files`** — per-file `(size, m

---

## Final answer as submitted

## How re-runs avoid repeating work

The pipeline caches at two points, both guarded by a **sidecar SQLite file** (`<output>.idxcache`) that sits alongside — but separate from — `docs.db`. It has to be separate because `docs.db` itself is thrown away and rebuilt from scratch on *every* run: `doxygen → copy → augment → os.replace` (`doxyguard_db/indexcache.py:7`). Since the final output is never mutated incrementally, the state that makes re-runs cheap can't live inside it — it lives in this sidecar, in three tables (`doxyguard_db/indexcache.py:9-24`):

- **`source_files`** — per-file `(size, mtime_ns, content_sha)` (`doxyguard_db/indexcache.py:70-75`).
- **`extract_cache`** — per-file AST/extraction payloads, content-addressed by `(content_sha, stage, stage_version, extra_key)` (`doxyguard_db/indexcache.py:76-83`).
- **`doxygen_cache`** — `tree_sha → (db_path, output_sha)`, letting an unchanged tree skip re-running doxygen entirely (`doxyguard_db/indexcache.py:20-24`, `doxyguard_db/indexcache.py:51-58`).

**Why kept there, not in `docs.db`:** `docs.db` is a disposable artifact regenerated whole each build; a cache has to survive across that regeneration, so it must be a separate file the next run opens before `docs.db` exists.

**Mechanism for "unchanged, skip it":**
1. Cheap prefilter — `size_bytes`+`mtime_ns` match ⇒ skip re-hashing and reuse the stored `content_sha` (`doxyguard_db/indexcache.py:206-218`). If either differs, the file is actually re-read and sha256'd (`doxyguard_db/treescan.py:90-104`).
2. **Content sha, not mtime, is authoritative** — a `touch` with no edit, or a branch checkout that restores identical bytes, both still compare `content_sha` equal and count as unchanged (`doxyguard_db/treescan.py:8-12`, `doxyguard_db/indexcache.py:243-246`).
3. `scan()` buckets every enumerated file into unchanged/modified/added/removed by comparing this run's identities against the previous run's (`doxyguard_db/indexcache.py:224-250`).
4. Whether **doxygen itself** needs to re-run is decided by `tree_sha` — a hash folding `DOXYGUARD_DB_BUILD_VERSION`, the exact Doxyfile content, `--extra-input`/`--extra-exclude`, and the sorted `(path, content_sha)` set (`doxyguard_db/indexcache.py:364-379`). An unchanged tree hits `doxygen_cache` and the doxygen subprocess is skipped outright.
5. Whether a **per-file extraction stage** (AST recovery, locks, threads, call edges, …) needs to re-parse a file is decided per `(content_sha, stage, stage_version, extra_key)` via `extract_has`/`extract_get`/`extract_put` (`doxyguard_db/indexcache.py:293-358`).
6. Manifest inputs (`--thread-patterns`, `--shared-key-patterns`, `--mqtt-dispatch`, `--data-model`, `--guard-config`, or an equivalent `.doxyguard-db.yaml` section) are folded into `extra_key` by hashing their content (`doxyguard_db/treescan.py:112-131`), so editing a declaration invalidates exactly the stages it feeds.

## Everything that can invalidate previously-done work

- **File content changes** (sha256 differs) → that file is `modified`; its extraction payloads and, via `tree_sha`, doxygen's own run are invalidated (`doxyguard_db/indexcache.py:243-246`, `364-379`).
- **File removed** → dropped on `commit()`, so it can no longer serve a hit and its absence changes `tree_sha` (`doxyguard_db/indexcache.py:510-525`).
- **`DOXYGUARD_DB_BUILD_VERSION` bump** → wipes `source_files`, `extract_cache`, and `doxygen_cache` in full — "belt-and-braces, drop everything rather than reason about which stage moved" (`doxyguard_db/indexcache.py:158-188`).
- **A stage's own `stage_version` bump** → invalidates only that stage's `extract_cache` rows, since it's part of the cache key (`doxyguard_db/indexcache.py:76-83`).
- **Manifest/declaration content changes** (thread/shared-key/mqtt/data-model/guard-config) → change `extra_key`, invalidating just the affected stage's entries (`doxyguard_db/treescan.py:112-131`).
- **Doxyfile / INPUT / EXCLUDE / extra-input / extra-exclude changes** → change `tree_sha`, forcing doxygen to re-run even if no source file changed (`doxyguard_db/indexcache.py:364-379`, `doxyguard_db/treescan.py:225-254`, `334-372`).
- **An unreadable file** → hashes to `""`, which is treated as perpetually changed rather than a wildcard match — fail toward a miss (`doxyguard_db/treescan.py:90-104`, explicit guard against `"" == ""` hits in `doxyguard_db/indexcache.py:444-448`).
- **Another build overwriting the shared doxygen output path** → `doxygen_get` re-hashes the on-disk output and compares it to the recorded `output_sha`; a mismatch (bug #399) is a miss even though the `tree_sha` row exists, because every config shares one output path/filename (`doxyguard_db/indexcache.py:385-435`).
- **`--rebuild` (`read_enabled=False`)** → every *prior* run's entries become unreadable (miss), though this run's own freshly-written entries are exempt so a forced full build still benefits from its own shared parse pass (`doxyguard_db/indexcache.py:94-100`, `273-283`).
- **Sidecar schema drift** (an older cache file missing `output_sha`) → `doxygen_cache` table is dropped and recreated rather than migrated, since it's pure cache (`doxyguard_db/indexcache.py:129-156`).

## What is NOT made incremental

Only two things are actually cached: **whether doxygen needs to re-run** (`doxygen_cache`, keyed by `tree_sha`) and **whether a given file's per-stage extraction needs recomputing** (`extract_cache`, keyed by content sha + stage + version). Everything downstream of that is rebuilt in full, every run, regardless of what changed:

- The assembly of `docs.db` itself — `copy_database` → `enrich_database` → `fix_doxygen_paths` → supplementary-doc ingestion → `os.replace` — is a full rebuild each time; there is no partial/merge write path into the output database (`doxyguard_db/indexcache.py:7-9`).
- The entire augmentation pipeline runs fully on every invocation against whatever memberdef rows exist: `build_call_edges`, macro-hop edges, AST call edges, callback/fnptr edges, lock extraction, declared dispatch, thread extraction, all shared-key/MQTT/event edge layers, requirement ingestion and `@req`/test-coverage edges, and the `mark_reachability` BFS (`doxyguard_db/cli.py:1-59`, steps 2–19). None of these stages check "did anything change" before running — they always re-derive their tables from the current doxygen output.
- Cached extraction payloads are stored **rowid-free** specifically because doxygen's own rowids are not stable across runs — so even a fully cache-hit AST payload must be re-resolved against the freshly generated `memberdef` table on every build (`doxyguard_db/indexcache.py:16-19`). Re-resolution itself is not incremental; only the parse/extraction work behind it is skipped.
- `report_stats`/`report_index_coverage` and the final summary are recomputed from scratch each run (`doxyguard_db/cli.py:21-22, 55`).

## Gaps

- I did not trace the exact code paths for `copy_database`/`enrich_database`/`build_call_edges` etc. beyond the `cli.py` pipeline-order docstring — I relied on that docstring's own claims (e.g. `enrich_database`'s "idempotent replace-on-rerun" behavior, referenced in `tests/test_enrichment.py`'s file doc) rather than reading each stage's body, since the question is about the incremental-cache boundary, not each stage's internals.
- `search(corpus=symbols)` for `indexcache`/`treescan` internals returned no function-level dossier hits directly (only file-level docs), so the detailed mechanism above came from `Read` of the two source files rather than `dossier`/`search`; the index's symbol search did correctly point me at the right two files first.
