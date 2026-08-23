# SPDX-License-Identifier: MIT
"""Sidecar index cache store making rebuilds incremental.

File identity hashing and tree enumeration live in the sibling `treescan`
module; this one owns the sidecar SQLite database and its invalidation rules.

clew.db is rebuilt from scratch on every run (doxygen → copy → augment →
`os.replace`), so the incrementality state cannot live inside it. It lives in a
sidecar SQLite file (`<output>.idxcache` by default) holding three tables:

  * `source_files`   — per-file identity (`size`, `mtime_ns`, `content_sha`).
    mtime+size is only a PREFILTER (skip re-hashing when both match); the
    sha256 of the file's bytes is the AUTHORITY, so a `touch` with no edit and
    a branch checkout that restores identical content both stay cache HITS.
  * `extract_cache`  — content-addressed per-file AST harvest payloads, keyed
    by (content_sha, stage, stage_version, extra_key). Payloads are rowid-FREE
    (they record source LINES + identifier text); rowid resolution happens on
    every build against the freshly generated memberdef table, because doxygen
    rowids are not stable across runs.
  * `doxygen_cache`  — tree_sha → the doxygen SQLite output that tree produced,
    so an unchanged tree skips the (non-incrementable) doxygen run entirely.
    EVERY KEY NAMES THE SAME PATH, which is why the row also carries
    `output_sha` — see `doxygen_get` for the false hit that came of trusting
    the path alone (#399).

Invalidation is deliberately trigger-happy — **when in doubt, MISS**. A false
miss costs time; a false hit ships a wrong database. `CLEW_BUILD_VERSION`
wipes the whole cache; each stage carries its own `STAGE_VERSION`; manifest
inputs (--thread-patterns / --shared-key-patterns / --mqtt-dispatch / ...) fold
their content hashes into the affected stage's `extra_key`.

@brief Sidecar incremental-index cache (file identity + AST payloads + doxygen).
@version 2
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ._common import logger
from .signature import CLEW_BUILD_VERSION
from .treescan import FileIdentity, ScanSummary, hash_file

## Split out of `_SCHEMA` so `_align_doxygen_cache` can rebuild this one table when an
## older sidecar predates a column. The other two have never changed shape.
_DOXYGEN_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS doxygen_cache (
    tree_sha   TEXT PRIMARY KEY,
    db_path    TEXT NOT NULL,
    output_sha TEXT NOT NULL,
    config_sha TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
"""

## The column set `doxygen_get`/`doxygen_put` require. A sidecar whose table differs is
## rebuilt rather than migrated — it is pure cache, so dropping it costs one doxygen run.
_DOXYGEN_CACHE_COLUMNS = frozenset(
    {"tree_sha", "db_path", "output_sha", "config_sha", "created_at"}
)

_SCHEMA = (
    """
CREATE TABLE IF NOT EXISTS cache_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_files (
    path        TEXT PRIMARY KEY,
    size_bytes  INTEGER NOT NULL,
    mtime_ns    INTEGER NOT NULL,
    content_sha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extract_cache (
    content_sha   TEXT NOT NULL,
    stage         TEXT NOT NULL,
    stage_version INTEGER NOT NULL,
    extra_key     TEXT NOT NULL DEFAULT '',
    payload       BLOB NOT NULL,
    PRIMARY KEY (content_sha, stage, stage_version, extra_key)
);
"""
    + _DOXYGEN_CACHE_DDL
)


## @brief Sidecar SQLite cache backing incremental rebuilds.
## @version 1
class IndexCache:
    """Owns the sidecar cache file and every read/write against it.

    `read_enabled=False` (from `--rebuild`) makes every lookup of a PRIOR run's
    entry MISS while still refreshing the stored entries, so one forced full
    build re-warms the cache. An entry this run wrote is exempt: `--rebuild`
    distrusts what is on disk from before, and a payload computed seconds ago in
    this process from these bytes by this code is not that. Without the
    exemption `--rebuild` would defeat gh#358's shared parse pass and go back to
    parsing every file once per stage.

    @brief Incremental-index sidecar cache.
    @version 2
    """

    ## @brief Open (creating if needed) the sidecar cache and load prior state.
    ## @version 5
    ## @dg_internal
    def __init__(self, cache_path: Path, repo_root: Path, read_enabled: bool = True) -> None:
        self.cache_path = cache_path
        self.repo_root = repo_root
        self.read_enabled = read_enabled
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(cache_path))
        self.conn.executescript(_SCHEMA)
        self._align_doxygen_cache()
        self._invalidate_on_build_version()
        self._previous: dict[str, FileIdentity] = self._load_source_files()
        self._current: dict[str, FileIdentity] = {}
        ## Extract keys WRITTEN by this run, and the ones already counted in
        ## hits/misses. The first makes `--rebuild` re-use this run's own work;
        ## the second keeps one (file, stage) pair from being counted twice now
        ## that the shared parse pass computes what the stages then read back.
        self._fresh: set[tuple[str, str, int, str]] = set()
        self._accounted: set[tuple[str, str, int, str]] = set()
        self.hits = 0
        self.misses = 0

    ## @brief Rebuild `doxygen_cache` when an older sidecar predates one of its columns.
    ## @version 1
    ## @dg_internal
    def _align_doxygen_cache(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` does NOTHING to a table that already exists, so a
        sidecar written before `output_sha` keeps its three-column shape and the first
        `doxygen_put` against it raises `no column named output_sha` — a crash on upgrade,
        in the one component whose whole job is to be discardable. The build-version wipe
        does not help: it deletes ROWS, not columns.

        Dropped rather than `ALTER TABLE ... ADD COLUMN`, because a back-filled row would
        have to invent an `output_sha` for output it never hashed, and inventing one is the
        false hit this column exists to prevent.

        @brief Drop and recreate the doxygen cache table on a column mismatch.
        @version 1
        """
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(doxygen_cache)")}
        if columns == _DOXYGEN_CACHE_COLUMNS:
            return
        logger.info(
            "index cache: doxygen_cache shape %s → %s — rebuilding that table",
            sorted(columns),
            sorted(_DOXYGEN_CACHE_COLUMNS),
        )
        self.conn.execute("DROP TABLE IF EXISTS doxygen_cache")
        self.conn.executescript(_DOXYGEN_CACHE_DDL)
        self.conn.commit()

    ## @brief Wipe every cached artifact when CLEW_BUILD_VERSION changed.
    ## @version 4
    ## @dg_internal
    def _invalidate_on_build_version(self) -> None:
        """A build-version bump means the pipeline's logic moved; belt-and-
        braces, drop everything rather than reason about which stage moved.

        @brief Whole-cache invalidation on a build-version bump.
        @version 3
        """
        row = self.conn.execute(
            "SELECT value FROM cache_meta WHERE key = 'build_version'",
        ).fetchone()
        current = str(CLEW_BUILD_VERSION)
        if row is not None and row[0] == current:
            return
        if row is not None:
            logger.info(
                "index cache: build version %s → %s — dropping all cached entries",
                row[0],
                current,
            )
        self.conn.execute("DELETE FROM source_files")
        self.conn.execute("DELETE FROM extract_cache")
        self.conn.execute("DELETE FROM doxygen_cache")
        self.conn.execute(
            "INSERT INTO cache_meta(key, value) VALUES('build_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (current,),
        )
        self.conn.commit()

    ## @brief Load the previous run's per-file identities.
    ## @return Mapping of repo-relative path to its stored FileIdentity.
    ## @version 1
    ## @dg_internal
    def _load_source_files(self) -> dict[str, FileIdentity]:
        return {
            row[0]: FileIdentity(row[1], row[2], row[3])
            for row in self.conn.execute(
                "SELECT path, size_bytes, mtime_ns, content_sha FROM source_files",
            )
        }

    ## @brief Identity of one file, re-hashing only when the prefilter misses.
    ## @return FileIdentity for the path, or None when it cannot be stat'ed.
    ## @version 1
    ## @dg_internal
    def _identity(self, rel: str, abs_path: Path) -> FileIdentity | None:
        try:
            stat = abs_path.stat()
        except OSError:
            return None
        prev = self._previous.get(rel)
        if (
            prev is not None
            and prev.size_bytes == stat.st_size
            and prev.mtime_ns == stat.st_mtime_ns
        ):
            return FileIdentity(stat.st_size, stat.st_mtime_ns, prev.content_sha)
        return FileIdentity(stat.st_size, stat.st_mtime_ns, hash_file(abs_path))

    ## @brief Hash a whole tree and classify it against the previous scan.
    ## @return ScanSummary bucketing every path unchanged/modified/added/removed.
    ## @version 2
    ## @req REQ-DDB-INDEX-002
    def scan(self, files: dict[str, Path]) -> ScanSummary:
        """Populate this run's identity map from `enumerate_tree` output and
        bucket the result. Content sha decides; mtime+size only decide whether
        re-hashing is needed.

        @brief Scan + classify the indexed tree.
        @version 2
        """
        unchanged: list[str] = []
        modified: list[str] = []
        added: list[str] = []
        for rel, abs_path in files.items():
            identity = self._identity(rel, abs_path)
            if identity is None:
                continue
            self._current[rel] = identity
            prev = self._previous.get(rel)
            if prev is None:
                added.append(rel)
            elif prev.content_sha == identity.content_sha:
                unchanged.append(rel)
            else:
                modified.append(rel)
        removed = sorted(set(self._previous) - set(files))
        summary = ScanSummary(sorted(unchanged), sorted(modified), sorted(added), removed)
        logger.info("index cache: %s", summary.describe())
        return summary

    ## @brief Content sha for one indexed path, computing it on demand.
    ## @return Hex sha256 of the file, or None when it cannot be read.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def sha_for(self, rel: str, abs_path: Path) -> str | None:
        """Serve the sha recorded by `scan`, or stat+hash a path the scan never
        saw (doxygen can index a file outside the enumerated INPUT roots — e.g.
        a followed include) and remember it for the next run.

        @brief Look up (or compute) one file's content sha.
        @version 1
        """
        known = self._current.get(rel)
        if known is not None:
            return known.content_sha
        identity = self._identity(rel, abs_path)
        if identity is None:
            return None
        self._current[rel] = identity
        return identity.content_sha

    ## @brief Whether a lookup may be served from the store at all.
    ## @param key The full (content_sha, stage, stage_version, extra_key) tuple.
    ## @return True when reads are enabled or this run wrote the entry itself.
    ## @version 1
    ## @dg_internal
    def _readable(self, key: tuple[str, str, int, str]) -> bool:
        """@brief Apply the --rebuild rule, exempting this run's own writes.

        @version 1
        """
        return self.read_enabled or key in self._fresh

    ## @brief Whether a per-file extraction payload is present and readable.
    ## @param content_sha The file's content sha.
    ## @param stage The stage tag.
    ## @param stage_version The stage's extraction version.
    ## @param extra_key The manifest-derived key component.
    ## @return True when a lookup would hit.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def extract_has(
        self,
        content_sha: str,
        stage: str,
        stage_version: int,
        extra_key: str,
    ) -> bool:
        """Existence WITHOUT decoding the payload, for the shared parse pass —
        which asks ten questions per file and wants none of the answers, only
        which stages still need computing.

        @brief Cheap presence check for one stage payload.
        @version 1
        """
        if not self._readable((content_sha, stage, stage_version, extra_key)):
            return False
        row = self.conn.execute(
            "SELECT 1 FROM extract_cache WHERE content_sha = ? AND stage = ? "
            "AND stage_version = ? AND extra_key = ?",
            (content_sha, stage, stage_version, extra_key),
        ).fetchone()
        return row is not None

    ## @brief Fetch a cached per-file extraction payload.
    ## @return The decoded payload, or None on a miss.
    ## @version 3
    ## @req REQ-DDB-INDEX-002
    def extract_get(
        self,
        content_sha: str,
        stage: str,
        stage_version: int,
        extra_key: str,
    ) -> Any | None:
        if not self._readable((content_sha, stage, stage_version, extra_key)):
            return None
        row = self.conn.execute(
            "SELECT payload FROM extract_cache WHERE content_sha = ? AND stage = ? "
            "AND stage_version = ? AND extra_key = ?",
            (content_sha, stage, stage_version, extra_key),
        ).fetchone()
        return None if row is None else json.loads(row[0])

    ## @brief Store a per-file extraction payload under its content identity.
    ## @version 3
    ## @req REQ-DDB-INDEX-002
    def extract_put(
        self,
        content_sha: str,
        stage: str,
        stage_version: int,
        extra_key: str,
        payload: Any,
    ) -> None:
        self._fresh.add((content_sha, stage, stage_version, extra_key))
        self.conn.execute(
            "INSERT OR REPLACE INTO extract_cache"
            "(content_sha, stage, stage_version, extra_key, payload) VALUES (?, ?, ?, ?, ?)",
            (
                content_sha,
                stage,
                stage_version,
                extra_key,
                json.dumps(payload, separators=(",", ":")),
            ),
        )

    ## @brief Hash of everything that determines the doxygen run's output.
    ## @return Hex sha256 over the scanned tree, Doxyfile bytes, and forced flags.
    ## @version 4
    ## @req REQ-DDB-INDEX-002
    def tree_sha(self, doxyfile_content: str, extra: list[str]) -> str:
        """Fold the sorted (path, content_sha) set together with the exact
        Doxyfile content the pipeline pipes to doxygen (which already carries
        the forced flags and any --extra-input/--extra-exclude lines).

        @brief Compute the doxygen-cache tree hash.
        @version 5
        """
        digest = self._config_digest(doxyfile_content, extra)
        for rel in sorted(self._current):
            digest.update(f"\n{rel}\x00{self._current[rel].content_sha}".encode())
        return digest.hexdigest()

    ## @brief The part of the tree hash that describes the CONFIGURATION, not the files.
    ## @param doxyfile_content The exact Doxyfile piped to doxygen.
    ## @param extra Additional key material.
    ## @return A seeded hasher, ready for the per-file fold or a direct hexdigest.
    ## @version 1
    ## @dg_internal
    def _config_digest(self, doxyfile_content: str, extra: list[str]) -> Any:
        """SHARED WITH `tree_sha` ON PURPOSE. `config_sha` must be a strict prefix of what
        `tree_sha` folds, or the two could disagree about what counts as a configuration and
        the splice would key off a different notion of sameness than the skip does. Rendering
        it in one place is what makes them impossible to diverge.

        @brief Seed a digest with the configuration only.
        @return The seeded hasher.
        @version 1
        """
        digest = hashlib.sha256()
        digest.update(f"build_version={CLEW_BUILD_VERSION}\n".encode())
        digest.update(doxyfile_content.encode("utf-8", errors="replace"))
        for item in extra:
            digest.update(f"\x1f{item}".encode())
        return digest

    ## @brief Identify the build CONFIGURATION, independent of the file set.
    ## @param doxyfile_content The exact Doxyfile piped to doxygen.
    ## @param extra Additional key material.
    ## @return Hex sha256 over the Doxyfile bytes, forced flags and build version.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def config_sha(self, doxyfile_content: str, extra: list[str]) -> str:
        """WHAT THE INCREMENTAL SPLICE MAY SAFELY SPLICE INTO. `tree_sha` changes on any file
        edit, which is exactly when a splice is wanted, so it cannot be the key for "is the
        previous output compatible with this build". This one changes only when the
        CONFIGURATION moves — Doxyfile bytes, forced flags, declared scope, PREDEFINED.

        THIS EXISTS BECAUSE OMITTING IT RE-SHIPPED #399. The first version of `doxygen_any`
        served the newest digest-verified output regardless of the key that produced it, which
        is precisely the aliasing `doxygen_get` was hardened against: withdrawing an
        `index_scope` statement served the NARROWER earlier output, so a widened scope got the
        file inventory back while its functions stayed missing. An existing integration test
        caught it at commit time, not this module's own tests.

        @brief Compute the configuration hash.
        @return Hex digest.
        @version 1
        """
        return self._config_digest(doxyfile_content, extra).hexdigest()

    ## @brief Look up a previously generated doxygen SQLite output.
    ## @return Path to the cached doxygen db when it still holds THIS key's output, else None.
    ## @version 3
    ## @req REQ-DDB-INDEX-002
    def doxygen_get(self, tree_sha: str) -> Path | None:
        """VERIFIED BY CONTENT, NOT BY EXISTENCE (#399). Every key in this table names the
        SAME `db_path`: doxygen's output directory is derived from `--index-cache`/`--output`
        alone (`cli._doxygen_out_dir`) and its filename is fixed
        (`doxygen.doxygen_db_path`), so N configurations of one repo produce N rows all
        pointing at one file that each build OVERWRITES. The old hit condition was "a row
        exists AND the path exists", which is true of every key the moment ANY of them has
        run — so a key was served whatever bytes happened to be there last.

        Measured both directions, which is what pins it as aliasing rather than staleness:
        withdrawing a `predefined` statement served the WIDER earlier output (the gated
        function stayed indexed after the macro was withdrawn), and withdrawing an
        `index_scope` statement served the NARROWER earlier output (`extra/` stayed missing
        after the scope was widened). Not "the newer output wins" — "whichever output was
        written last wins, whatever its key said".

        Comparing the recorded digest against the file's current one makes the hit
        conditional on the file BEING this key's output, whichever process last wrote it.

        MEASURED COST, one sha256 of the doxygen database per build: on this repo's own index
        that database is 6.9 MB and hashes in 6-10 ms, which is 0.33% of a 3.0 s warm build
        and is dwarfed by the tree scan beside it — the same build already hashes every
        source file, and the doxygen output is one file. A cold build it saves is 10.4 s here
        and tens of seconds on a large C++ target (#363). The skip is kept; it is now only
        taken when it is right.

        @brief Serve a cached doxygen output only under the key that produced it.
        @version 1
        """
        if not self.read_enabled:
            return None
        row = self.conn.execute(
            "SELECT db_path, output_sha FROM doxygen_cache WHERE tree_sha = ?",
            (tree_sha,),
        ).fetchone()
        if row is None:
            return None
        path, recorded = Path(row[0]), str(row[1])
        if not path.exists():
            return None
        current = hash_file(path)
        if current != recorded:
            logger.info(
                "index cache: %s no longer holds this configuration's doxygen output "
                "(recorded %s, found %s) — another build overwrote it, so re-running doxygen",
                path,
                recorded[:12],
                current[:12] or "unreadable",
            )
            return None
        return path

    ## @brief How many incremental splices have run since the last whole-tree doxygen build.
    ## @return The generation count, 0 when unknown.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def splice_generation(self) -> int:
        """MEASURED DRIFT IS WHY THIS EXISTS, not caution in the abstract. A spliced database
        is not bit-identical to a full rebuild: on this repository a modification-only refresh
        carried ONE call edge a full rebuild does not emit, out of 5168, with nothing missing.
        The cause is doxygen resolving names against the files it can SEE, so a subset can
        attribute an intra-file call to a different memberdef row than the whole tree does.

        One stale edge in five thousand is a fair price for a 3.2x cheaper refresh. A hundred
        splices' worth of accumulated stale edges is not, and nothing about a splice bounds
        the accumulation on its own. Counting generations turns unbounded drift into a known
        ceiling: the caller refuses to splice past the limit and pays for one full rebuild,
        which resets the count.

        @brief Read the splice generation counter.
        @return Generations since the last full build.
        @version 1
        """
        row = self.conn.execute(
            "SELECT value FROM cache_meta WHERE key = 'splice_generation'"
        ).fetchone()
        return int(row[0]) if row and str(row[0]).isdigit() else 0

    ## @brief Advance or clear the splice generation counter.
    ## @param reset True after a whole-tree build, which makes the index exact again.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def record_splice(self, reset: bool = False) -> None:
        """@brief Increment the splice generation, or zero it after a full build.
        @version 1
        """
        value = 0 if reset else self.splice_generation() + 1
        self.conn.execute(
            "INSERT INTO cache_meta(key, value) VALUES('splice_generation', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(value),),
        )

    ## @brief Serve the newest verified doxygen output built under THIS configuration.
    ## @param config_sha The current configuration hash; only matching output is served.
    ## @return Path to a usable previous output, or None when none verifies.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def doxygen_any(self, config_sha: str) -> Path | None:
        """The newest cached doxygen output that still holds the bytes it was recorded with,
        WHATEVER key produced it. `doxygen_get` answers "is this exact configuration's output
        still here", which is the right question for skipping the stage entirely. The
        incremental splice asks a different one: "is there a previous whole-tree output I can
        splice INTO", and the answer is useful even when the tree hash has moved — that is
        precisely the case where a splice is wanted.

        Verified by digest for the same reason `doxygen_get` is (#399): every key in this
        table names the SAME `db_path`, so existence alone proves nothing about whose output
        the file currently holds. A row whose digest no longer matches is skipped rather than
        served, because splicing into an unrecognised database would silently mix two
        configurations' rows and report success.

        @brief Serve the newest verified doxygen output, any key.
        @return Path to a usable previous output, or None.
        @version 1
        """
        if not self.read_enabled:
            return None
        for raw_path, recorded in self.conn.execute(
            "SELECT db_path, output_sha FROM doxygen_cache WHERE config_sha = ? AND config_sha != '' "
            "ORDER BY created_at DESC",
            (config_sha,),
        ):
            path = Path(str(raw_path))
            if path.exists() and hash_file(path) == str(recorded):
                return path
        return None

    ## @brief Record which doxygen SQLite output a tree hash produced.
    ## @version 2
    ## @req REQ-DDB-INDEX-002
    def doxygen_put(self, tree_sha: str, db_path: Path, config_sha: str = "") -> None:
        """Records the output's DIGEST alongside its path, which is what lets `doxygen_get`
        tell this key's output from the next key's overwrite of the same file (#399).

        A file that will not hash is NOT recorded at all. `hash_file` returns "" for an
        unreadable file, so storing that would make a later unreadable read compare
        `"" == ""` and HIT — the empty string as a wildcard, which is precisely the false
        hit this column exists to close.

        @brief Store a doxygen output path with the digest of what it held.
        @version 1
        """
        output_sha = hash_file(db_path)
        if not output_sha:
            logger.warning(
                "index cache: could not hash the doxygen output at %s — not caching it, so "
                "the next build re-runs doxygen rather than trusting an unverifiable file",
                db_path,
            )
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO doxygen_cache(tree_sha, db_path, output_sha, config_sha, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (tree_sha, str(db_path), output_sha, config_sha, int(time.time())),
        )

    ## @brief Count one cache hit or miss for the end-of-build summary.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def record(self, hit: bool) -> None:
        if hit:
            self.hits += 1
        else:
            self.misses += 1

    ## @brief Count one (file, stage) payload once per build, however often it is served.
    ## @param content_sha The file's content sha.
    ## @param stage The stage tag.
    ## @param stage_version The stage's extraction version.
    ## @param extra_key The manifest-derived key component.
    ## @param hit True when the payload was served from the store.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def record_pair(
        self,
        content_sha: str,
        stage: str,
        stage_version: int,
        extra_key: str,
        hit: bool,
    ) -> None:
        """IDEMPOTENT, and that is the whole point. Since gh#358 a payload is
        normally COMPUTED by the shared parse pass and then READ BACK by the stage
        that needs it, so the naive count would report every cold build as both
        fully missed and fully hit — and `misses` is published as the index's
        `files_reprocessed`, which `status` shows to an agent deciding whether to
        trust the answer. First outcome for a pair wins; the pair is the unit.

        @brief Record one per-file-per-stage outcome, at most once.
        @version 1
        """
        key = (content_sha, stage, stage_version, extra_key)
        if key in self._accounted:
            return
        self._accounted.add(key)
        self.record(hit)

    ## @brief Persist this run's file identities and commit; then close.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def commit(self) -> None:
        """Replace `source_files` with this run's scan — rows for files that
        disappeared are dropped, so a removed file stops hitting the cache.

        @brief Flush the cache to disk.
        @version 1
        """
        self.conn.execute("DELETE FROM source_files")
        self.conn.executemany(
            "INSERT OR REPLACE INTO source_files(path, size_bytes, mtime_ns, content_sha) "
            "VALUES (?, ?, ?, ?)",
            [
                (rel, ident.size_bytes, ident.mtime_ns, ident.content_sha)
                for rel, ident in self._current.items()
            ],
        )
        self.conn.commit()
        logger.info(
            "index cache: %d per-file hits, %d misses (%s)",
            self.hits,
            self.misses,
            self.cache_path.name,
        )

    ## @brief Close the sidecar connection without committing.
    ## @version 1
    ## @req REQ-DDB-INDEX-002
    def close(self) -> None:
        self.conn.close()
