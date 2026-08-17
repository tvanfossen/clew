# Q7 — src — sonnet — run 1

## Answer

### The mechanism: content-addressed sidecar cache, keyed independently at three granularities

`docs.db` itself is **rebuilt from scratch every run** (doxygen → copy → augment → atomic `os.replace`) — the incrementality state cannot live inside it, so it lives in a separate SQLite sidecar file, `<output>.idxcache` by default (`doxyguard_db/indexcache.py:7-9`, `doxyguard_db/cli.py:2033,2112`).

That sidecar holds three tables (`doxyguard_db/indexcache.py:9-24`):

1. **`source_files`** — per-file identity: `size_bytes`, `mtime_ns`, `content_sha` (`doxyguard_db/indexcache.py:70-75`). `size+mtime_ns` is only a cheap prefilter to skip re-hashing; the sha256 of the file's bytes is the actual authority for "changed or not" (`doxyguard_db/treescan.py:8-12`, `indexcache.py:206-218`). This is why a `touch` with no edit, or a branch checkout that restores identical bytes, both register as unchanged (`treescan.py:11-12`).
2. **`extract_cache`** — per-file AST-harvest payloads keyed by `(content_sha, stage, stage_version, extra_key)` (`indexcache.py:76-83`). Payloads are deliberately **rowid-free** — they store source lines/identifier text, and rowid resolution happens fresh every build against the newly generated `memberdef` table, because doxygen rowids aren't stable run to run (`indexcache.py:15-19`).
3. **`doxygen_cache`** — `tree_sha → (db_path, output_sha)`, letting an unchanged tree skip re-running doxygen entirely, the most expensive stage (`indexcache.py:20-24`, `52-58`). `tree_sha` folds the build version, the exact Doxyfile bytes fed to doxygen, and the sorted `(path, content_sha)` set together (`indexcache.py:364-379`).

### Why it's kept in a sidecar, not in docs.db

Two reasons, both explicit in the module docstring: docs.db is regenerated wholesale every run so state that needs to *persist across* runs can't live in it (`indexcache.py:7-9`); and the per-file payloads are content-addressed rather than tied to any particular database's rowids, which lets them survive the fact that doxygen assigns new, unstable rowids on every parse (`indexcache.py:15-19`).

### What makes previously-done work count as no longer usable (every invalidation trigger)

- **File content changed** — `content_sha` differs from what's stored for that path; `mtime_ns`/`size` only gate whether re-hashing happens, never the hit/miss decision itself (`indexcache.py:206-218,243-246`).
- **File added** — no prior identity row exists for the path (`indexcache.py:241-242`).
- **File removed** — a path in the previous scan is absent from the current tree; its `source_files` row is dropped on commit, so it stops ever hitting again (`indexcache.py:247`, `510-516`).
- **`DOXYGUARD_DB_BUILD_VERSION` bump** — wipes `source_files`, `extract_cache`, and `doxygen_cache` unconditionally; deliberately belt-and-braces rather than reasoning about which stage moved (`indexcache.py:158-188`, rationale in `doxyguard_db/signature.py:16-18,26-359` — each numbered comment records *why* a given bump invalidates).
- **Per-stage `stage_version` bump** — invalidates only that stage's `extract_cache` rows (keyed into the tuple), without forcing a whole-cache wipe (`indexcache.py:76-83`, e.g. signature.py's notes at builds 43→44/44→45/46/48 on `stage_version` moving independently of `DOXYGUARD_DB_BUILD_VERSION`).
- **Manifest/declared-config content changes** (`--thread-patterns`, `--shared-key-patterns`, `--mqtt-dispatch`, `--data-model`, `--guard-config`, or an equivalent section of `.doxyguard-db.yaml`) — hashed via `manifest_key`/`extra_key` and folded into the affected stage's cache key, so editing a manifest re-runs exactly the stages it feeds (`treescan.py:107-131`, `indexcache.py:28-30`).
- **Doxyfile content or forced flags change** — folded into `tree_sha`, so any INPUT/EXCLUDE/predefined/preprocessor change invalidates the doxygen-cache entry (`indexcache.py:364-379`).
- **The cached doxygen output no longer matches its recorded digest** (`doxygen_get`) — because every `tree_sha` key names the *same* on-disk `db_path` (doxygen's output location is derived only from `--index-cache`/`--output`), a stale/aliased entry is detected by re-hashing the file and comparing to the recorded `output_sha`; a mismatch forces a miss even though the row still "exists" (`indexcache.py:381-435`, rationale gh#399).
- **An unhashable/unreadable file** — `hash_file` returns `""` on OSError, which is treated as "perpetually changed," never trusted as a match (`treescan.py:90-104`); similarly an unhashable doxygen output is simply not cached at all rather than risking a false hit (`indexcache.py:440-459`).
- **`--rebuild` (`read_enabled=False`)** — makes every lookup of a *prior* run's entry miss (forces a full re-warm), while still allowing entries this same run just wrote to be served, so `--rebuild` doesn't undo the shared single-parse-per-file optimization within one run (`indexcache.py:94-100,278-283`).
- **`doxygen_cache` table shape mismatch** (an older sidecar predates a column, e.g. missing `output_sha`) — the whole table is dropped and recreated rather than migrated, since it's pure cache and costs only one doxygen re-run (`indexcache.py:129-156`).

Overall invalidation policy is explicitly "trigger-happy": *when in doubt, miss* — a false miss costs time, a false hit ships a wrong database (`indexcache.py:26`).

### What is NOT made incremental

Every **cross-file / whole-graph** augmentation stage is always fully recomputed on every build, regardless of cache state — reachability, thread membership, boundary annotation, requirements, and (by the same logic) call/dataflow edges, because they depend on the entire assembled graph rather than any single file (`doxyguard_db/cli.py:1282-1284`, doc comment: *"every CROSS-FILE stage below... is always recomputed, because they depend on the whole assembled graph"*). Only the **per-file AST extraction stages** are incremental via the cache (`cli.py:1291-1293`, gh#358 shared-parse-pass note).

Additionally:
- `docs.db` itself is never incrementally patched — it's built fresh into a temp path and atomically swapped in (`indexcache.py:7-9`; `cli.py:2033,2112`).
- The **running MCP server process's own code/logic is not incremental at all** — it's fixed at import/launch time. A source change is invisible to it until restart; `mcp_server/freshness.py:14-16,90-104,156-161` computes a `code` staleness axis specifically because rebuilding through a stale server can *silently downgrade* the index (drop whole layers) while reporting success (`freshness.py:30-40`). This is explicitly *not* fixed by hot-reloading modules — that's rejected as unsafe (`freshness.py:366-369`).

## Gaps

- I did not trace every individual stage's `stage_version` history in exhaustive detail (there are ~15+ numbered rationale entries in `signature.py`); I cited representative ones rather than all of them, since the mechanism (bump invalidates that stage's `extract_cache` rows) is uniform.
- I did not verify from source exactly which augmentation stages besides reachability/threads/requirements/boundaries fall under "cross-file, always recomputed" — the docstring at `cli.py:1282-1284` names those four as examples but doesn't give an exhaustive enumeration, and I did not individually confirm each remaining stage (e.g. `shared_key_edges`, `locks`, `kconfig_gates`) against that claim by reading each module.
