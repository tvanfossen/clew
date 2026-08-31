# SPDX-License-Identifier: MIT
"""Verification suite for the incremental/partial index cache.

Moved here from `tests/test_indexcache.py` when `sample/` was deleted. Every
test builds a REAL repo END TO END (real doxygen + real tree-sitter) twice
against a scratch copy, because the cache's entire job is to classify a real
tree of real files across two real builds — a synthetic database has no tree to
classify.

The load-bearing test is `test_warm_rebuild_is_deterministic`: a cache-warm
rebuild must produce a byte-identical database. A false cache hit is the one
failure mode that ships a WRONG database, so the rest of the suite pins the
invalidation rules that prevent it.

**Why the pinned doxygen-guard checkout is a better target than `sample/` was:**

  * 67 files instead of 26, so "one file changed" is a proportionally smaller
    edit and a cache that quietly re-does everything is easier to catch.
  * It ships **no Doxyfile**, so every build here goes through the #33
    synthesis path. `sample/` always supplied one, so the synthesized-Doxyfile
    build was never incrementally tested at all.
  * Its indexed scope is **Python**. `sample/` is pure C, so the `.py` branch of
    every cacheable AST stage (`ast_calls`, `fnptr`, `locks`, `py_entries`,
    `shared_key`, `threads`) had no incremental coverage before.

**Named accepted loss:** the old `_build` passed `--requirements` and
`--shared-key-patterns`, so a manifest sha fed the stage cache keys. No test
ever EDITED a manifest, so nothing asserted that invalidation — the manifests
only widened the compared table set. The target repo has neither convention, and
inventing a no-op manifest for it would be fixture theater, so they are dropped
rather than faked.

@brief Integration tests for clew.indexcache and the cached AST stages.
@version 2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import harvest
from clew.cli import JOBS_ENV, _build_argparser, _run_pipeline
from clew.indexcache import IndexCache

pytestmark = pytest.mark.integration

## An in-scope source file with a function name unique across the whole index
## (`_rev_parse_head`), so the edit test's new call edge is unambiguous.
EDIT_TARGET = "src/doxygen_guard/git.py"

## An in-scope source file whose functions appear nowhere else, so the deletion
## test can prove rows dropped rather than merely moved.
DELETE_TARGET = "src/doxygen_guard/ts_languages.py"

## A function defined ONLY in DELETE_TARGET.
DELETE_TARGET_FUNCTION = "_looks_like_cpp_header"

## Appended by the edit test: a documented function whose body calls exactly one
## existing function in the same file. Doxygen indexes it (giving the AST layer a
## rowid to resolve against) only because it carries a real doxygen comment.
NEW_FUNCTION = "head_revision_probe"
NEW_FUNCTION_CALLEE = "_rev_parse_head"
NEW_FUNCTION_SOURCE = (
    "\n\n## @brief Report the current HEAD revision (integration probe).\n"
    "#  @version 1.0\n"
    f"def {NEW_FUNCTION}() -> str:\n"
    f"    return {NEW_FUNCTION_CALLEE}()\n"
)


## @brief Run one full pipeline build against a staged target repo.
## @param root Staged repo root to index.
## @param out Output database path.
## @param cache Sidecar cache path to use, or None to take the default beside `out`.
## @param no_cache Run wholly uncached, writing no sidecar at all.
## @param rebuild Ignore cached entries but still re-warm them.
## @return Path to the built database.
## @version 3
def _build(
    root: Path,
    out: Path,
    cache: Path | None = None,
    no_cache: bool = False,
    rebuild: bool = False,
) -> Path:
    """No Doxyfile is named: the target ships none, so the default `from-guard` scope derives
    it from the repo's doxygen-guard hook and synthesizes one (#33).

    THE CACHE CONTROLS ARE NAMED ARGUMENTS, NOT ARGV, since the 22->6 collapse. `--rebuild`
    survived and is still typed on the command line here, because it is what an operator has;
    `--index-cache` and `--no-index-cache` did not, and this file is the reason the CAPABILITY
    had to survive them. Pointing two builds with DIFFERENT `--output` paths at ONE sidecar is
    how every warm-reuse assertion below proves reuse independent of the database path — the
    default sidecar is derived from `--output`, so without the override a "warm" build would
    be reading a cache it had just created. That is a test technique rather than an operator
    workflow, which is exactly why it kept the dest and lost the flag.

    @brief Execute the build pipeline against the pinned target.
    @version 3
    """
    argv = ["--repo-root", str(root), "--output", str(out)]
    if rebuild:
        argv.append("--rebuild")
    args = _build_argparser().parse_args(argv)
    if cache is not None:
        args.index_cache = str(cache)
    args.no_index_cache = no_cache
    _run_pipeline(args)
    return out


## @brief Dump every user table's rows in a sorted, comparable form.
## @param db Database to snapshot.
## @return Mapping of table name to its sorted row representations.
## @version 1
def _dump(db: Path) -> dict[str, list[str]]:
    """@brief Snapshot a database's full contents for equality assertions.

    @version 1
    """
    conn = sqlite3.connect(str(db))
    conn.text_factory = bytes
    out: dict[str, list[str]] = {}
    for (raw_name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
    ).fetchall():
        table = raw_name.decode()
        if table.startswith("sqlite_"):
            continue
        rows = conn.execute(f"SELECT * FROM [{table}]").fetchall()
        out[table] = sorted(repr(row) for row in rows)
    conn.close()
    return out


## The `build_meta` namespace gh#9 added to record what a build COST. Everything
## under it is a measurement OF THE BUILD, never content OF THE INDEX, and every
## member of it is expected to differ between any two builds — three because they
## read a wall clock (`at_epoch`, `duration_ms`, the per-stage `stages` breakdown)
## and two because making them differ is the cache's entire purpose (`cache_hits`,
## `payloads_recomputed`: a cold build recomputes everything and hits nothing, a warm
## one the reverse). Comparing them would assert that incrementality does not work.
_BUILD_COST_PREFIX = "refresh."

## `_dump` renders each row as `repr(tuple_of_bytes)`, so a cost row begins exactly
## like this. Matched as a prefix on the rendered row rather than re-querying, so the
## comparison and the exclusion read the SAME snapshot — a second query could see a
## different database state and exclude a row that was never compared.
_BUILD_COST_ROW_PREFIX = f"(b'{_BUILD_COST_PREFIX}"

## Every key `cli._stamp_refresh_metrics` can write. PINNED here, and asserted
## present, so the exclusion below cannot quietly widen: a sixth cost key, or the
## stamping disappearing altogether, fails the test that excludes them instead of
## being absorbed. `cache_hits`/`payloads_recomputed` are ABSENT under
## `--no-index-cache` by design (no cache ran, so zero would be a lie), which is why
## each test states its own expected subset rather than sharing one.
_BUILD_COST_KEYS = {
    "refresh.at_epoch",
    "refresh.cache_hits",
    "refresh.duration_ms",
    "refresh.payloads_recomputed",
    "refresh.stages",
}

## The three that every build writes, cache or no cache.
_BUILD_COST_KEYS_ALWAYS = {"refresh.at_epoch", "refresh.duration_ms", "refresh.stages"}


## @brief Remove the measured-cost rows from a dump, reporting which were removed.
## @param dump A `_dump` result, mutated in place.
## @return The `build_meta` keys that were excluded.
## @version 1
def _strip_build_cost(dump: dict[str, list[str]]) -> set[str]:
    """RETURNS the removed key set rather than swallowing it, so a caller can assert
    what it excluded. An exclusion nobody checks is how a comparison stops comparing:
    the whole `build_meta` row set would still be present in the dump and the test
    would still read as byte-exact over it.

    @brief Drop `refresh.*` rows and name them.
    @version 1
    """
    kept: list[str] = []
    removed: set[str] = set()
    for row in dump["build_meta"]:
        if row.startswith(_BUILD_COST_ROW_PREFIX):
            removed.add(row.split("'")[1])
        else:
            kept.append(row)
    dump["build_meta"] = kept
    return removed


## @brief All (caller_name, callee_name) call edges in a built database.
## @param db Database to read.
## @return Set of resolved/fuzzy call-edge name pairs.
## @version 1
def _call_edge_names(db: Path) -> set[tuple[str, str]]:
    """@brief Read call_edges back as name pairs (rowids aren't stable).

    @version 1
    """
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT DISTINCT a.name, b.name FROM call_edges e "
        "JOIN memberdef a ON a.rowid = e.caller_rowid "
        "JOIN memberdef b ON b.rowid = e.callee_rowid",
    ).fetchall()
    conn.close()
    return set(rows)


## @brief Count calls to the per-file tree-sitter parse during a build.
## @version 1
class _ParseCounter:
    """Wraps `harvest._ast_parse_one_file` to record which files re-parsed.

    @brief Per-file parse recorder.
    @version 1
    """

    __slots__ = ("_original", "paths")

    ## @brief Capture the original parse function and reset the record.
    ## @version 1
    def __init__(self) -> None:
        self.paths: list[str] = []
        self._original = harvest._ast_parse_one_file

    ## @brief Parse-function stand-in that records the path first.
    ## @return Whatever the wrapped parse function returns.
    ## @version 1
    def __call__(self, rel_path: str, *args, **kwargs):
        self.paths.append(rel_path)
        return self._original(rel_path, *args, **kwargs)


## @brief Install a parse counter for the duration of one build.
## @param monkeypatch pytest's attribute patcher.
## @return The active _ParseCounter.
## @version 1
@pytest.fixture
def parse_counter(monkeypatch: pytest.MonkeyPatch) -> _ParseCounter:
    """PINS THE BUILD TO ONE PROCESS, and that is a real limitation rather than a tidy-up.

    This counter works by patching a function IN THIS PROCESS. Since the shared parse became
    parallel by default, the parse it is counting happens in worker processes where the patch
    does not exist — so without `CLEW_JOBS=1` the counter observes zero parses and every
    assertion built on it becomes vacuous rather than failing honestly.

    WHAT THAT COSTS, stated plainly: these tests now describe the SERIAL path, not the shipped
    default. What carries the default is
    `tests/integration/test_parallel_shared_parse.py::test_parallel_shared_parse_is_index_identical`,
    which asserts the two produce the same index row for row. The invalidation rules pinned here
    are therefore verified on one path and transported to the other by that equality — which is
    exactly as strong as the equality test and no stronger.

    @brief Fixture patching the harvest driver's parse entry point, serial builds only.
    @version 2
    """
    monkeypatch.setenv(JOBS_ENV, "1")
    counter = _ParseCounter()
    monkeypatch.setattr(harvest, "_ast_parse_one_file", counter)
    return counter


## @brief The set of distinct files a build re-parsed, keyed repo-relatively.
## @param counter The parse counter installed for the build.
## @param root The staged repo root the build indexed.
## @return Repo-relative POSIX paths of every re-parsed file.
## @version 1
def _reparsed(counter: _ParseCounter, root: Path) -> set[str]:
    """`harvest.run_harvest` iterates doxygen's `path` table, and the form of
    `path.name` depends on how the build was configured: a repo-supplied
    Doxyfile with relative INPUT yields repo-relative names, while a SYNTHESIZED
    Doxyfile (this tier's case, #33) has absolute INPUT and doxygen records
    absolute names. Both are re-keyed to repo-relative POSIX here, so the
    assertions state "which file re-parsed" and not "which spelling doxygen
    happened to use".

    @brief Normalize re-parsed paths to repo-relative POSIX form.
    @version 1
    """
    root_posix = root.resolve().as_posix() + "/"
    out: set[str] = set()
    for raw in counter.paths:
        posix = Path(raw).as_posix()
        out.add(posix.removeprefix(root_posix))
    return out


## @brief Read the cache's extract_cache rows grouped by stage.
## @param cache_path Sidecar cache path.
## @return Mapping of (stage, stage_version) to row count.
## @version 1
def _stage_rows(cache_path: Path) -> dict[tuple[str, int], int]:
    """@brief Inspect which stage/version payloads the sidecar holds.

    @version 1
    """
    conn = sqlite3.connect(str(cache_path))
    rows = conn.execute(
        "SELECT stage, stage_version, COUNT(*) FROM extract_cache GROUP BY stage, stage_version",
    ).fetchall()
    conn.close()
    return {(stage, version): count for stage, version, count in rows}


## @brief Every path the sidecar currently claims to have indexed.
## @param cache_path Sidecar cache path.
## @return The raw `source_files.path` values.
## @version 1
def _cached_paths(cache_path: Path) -> set[str]:
    """@brief Read the sidecar's per-file identity keys.

    @version 1
    """
    conn = sqlite3.connect(str(cache_path))
    paths = {row[0] for row in conn.execute("SELECT path FROM source_files")}
    conn.close()
    return paths


## @brief A cache-warm rebuild must reproduce the database exactly.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @return None.
## @version 5
def test_warm_rebuild_is_deterministic(guard_repo: Path, tmp_path: Path) -> None:
    """THE critical property: incrementality may make a build faster, never
    different. Compares per-table row counts AND full row content, `meta`
    included — every table and every column is compared.

    Both builds go to the SAME output path, and the first result is snapshotted
    before the second overwrites it. That is what "rebuild" means to a user.

    Rebuilding in place makes doxygen genuinely skip, so its own wall-clock
    `meta` row is reproduced too.

    THE ONE EXCLUSION IS `build_meta`'s `refresh.*` NAMESPACE, added by gh#9 after
    this test was written — which is why the test failed on a working cache. Measured
    rather than assumed: those five keys are the ONLY difference between the two
    databases, over all 35 tables. Three of them read a wall clock; the other two are
    the cache's own scoreboard, so asserting they match would assert the cache does
    NOT work. The excluded set is asserted, so a sixth cost key or a lost stamping
    fails here rather than being silently absorbed.

    @brief Full build vs in-place warm rebuild produce identical databases.
    @version 5
    """
    cache = tmp_path / "shared.idxcache"
    out = tmp_path / "clew.db"
    cold = _dump(_build(guard_repo, out, cache=cache))
    warm = _dump(_build(guard_repo, out, cache=cache))

    # Both builds ran WITH a cache, so both stamp the full five.
    assert _strip_build_cost(cold) == _BUILD_COST_KEYS
    assert _strip_build_cost(warm) == _BUILD_COST_KEYS

    assert {t: len(r) for t, r in cold.items()} == {t: len(r) for t, r in warm.items()}
    assert cold == warm


## @brief mtime churn without a content change must still hit the cache.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @param parse_counter Installed per-file parse recorder.
## @return None.
## @version 2
def test_touch_without_edit_still_hits(
    guard_repo: Path,
    tmp_path: Path,
    parse_counter: _ParseCounter,
) -> None:
    """The sha256 of the bytes is the authority; mtime+size is only a
    prefilter. Touching every file bumps mtimes, forces re-hashing, and must
    still classify everything unchanged — no re-parse at all.

    @brief Touch-without-edit stays a cache hit.
    @version 2
    """
    cache = tmp_path / "shared.idxcache"
    _build(guard_repo, tmp_path / "cold.db", cache=cache)

    for path in guard_repo.rglob("*"):
        if path.is_file():
            path.touch()
    parse_counter.paths.clear()
    _build(guard_repo, tmp_path / "warm.db", cache=cache)

    assert parse_counter.paths == []


## @brief Editing one file re-parses only that file and updates only its edges.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @param parse_counter Installed per-file parse recorder.
## @return None.
## @version 2
def test_edit_one_file_reparses_only_that_file(
    guard_repo: Path,
    tmp_path: Path,
    parse_counter: _ParseCounter,
) -> None:
    """@brief One edited file → one re-parsed file, one changed edge set.

    @version 2
    """
    cache = tmp_path / "shared.idxcache"
    before = _call_edge_names(
        _build(guard_repo, tmp_path / "cold.db", cache=cache),
    )

    target = guard_repo / EDIT_TARGET
    target.write_text(target.read_text() + NEW_FUNCTION_SOURCE)
    parse_counter.paths.clear()
    after = _call_edge_names(
        _build(guard_repo, tmp_path / "warm.db", cache=cache),
    )

    # One file changed → exactly one file re-parsed (once per per-file stage).
    assert _reparsed(parse_counter, guard_repo) == {EDIT_TARGET}
    # The edited file's new edge appears...
    assert (NEW_FUNCTION, NEW_FUNCTION_CALLEE) in after
    # ...and nothing else moved.
    assert after - before == {(NEW_FUNCTION, NEW_FUNCTION_CALLEE)}
    assert before - after == set()


## @brief Bumping one stage's STAGE_VERSION invalidates only that stage.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @param monkeypatch pytest's attribute patcher.
## @param parse_counter Installed per-file parse recorder.
## @return None.
## @version 2
def test_stage_version_bump_invalidates_only_that_stage(
    guard_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parse_counter: _ParseCounter,
) -> None:
    """@brief A stage-version bump is a targeted, not global, invalidation.

    @version 2
    """
    from clew.call_edges import _CallSiteHarvester

    cache = tmp_path / "shared.idxcache"
    _build(guard_repo, tmp_path / "cold.db", cache=cache)
    baseline = _stage_rows(cache)
    # Read the CURRENT stage version rather than pinning a literal: the version
    # is bumped whenever the extraction changes, and this test is about the
    # invalidation mechanism, not about which number the stage happens to be on.
    current = _CallSiteHarvester.stage_version
    assert baseline[("ast_calls", current)] > 0

    monkeypatch.setattr(_CallSiteHarvester, "stage_version", current + 1)
    parse_counter.paths.clear()
    _build(guard_repo, tmp_path / "warm.db", cache=cache)
    bumped = _stage_rows(cache)

    # Only ast_calls re-parsed; every other stage served from cache.
    assert len(parse_counter.paths) == baseline[("ast_calls", current)]
    assert bumped[("ast_calls", current + 1)] == baseline[("ast_calls", current)]
    for key, count in baseline.items():
        assert bumped[key] == count  # untouched stages keep their entries


## @brief A deleted source file drops out of the index and the cache.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @return None.
## @version 2
def test_removed_file_drops_its_rows(guard_repo: Path, tmp_path: Path) -> None:
    """The cache assertion matches on a path SUFFIX rather than an exact string:
    `source_files` is keyed by whatever spelling the scan and the harvest driver
    used, and a synthesized Doxyfile makes doxygen report absolute names. Asking
    "no key names this file, in any spelling" is both stronger and immune to that.

    @brief Removing a file removes its functions and its cache identity.
    @version 2
    """
    cache = tmp_path / "shared.idxcache"
    _build(guard_repo, tmp_path / "cold.db", cache=cache)
    assert any(path.endswith(DELETE_TARGET) for path in _cached_paths(cache))

    (guard_repo / DELETE_TARGET).unlink()
    warm = _build(guard_repo, tmp_path / "warm.db", cache=cache)

    conn = sqlite3.connect(str(warm))
    names = {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind = 'function'")}
    conn.close()
    assert DELETE_TARGET_FUNCTION not in names

    assert not any(path.endswith(DELETE_TARGET) for path in _cached_paths(cache))


## @brief --no-index-cache writes no sidecar and always does full work.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @param parse_counter Installed per-file parse recorder.
## @return None.
## @version 2
def test_no_index_cache_does_full_work(
    guard_repo: Path,
    tmp_path: Path,
    parse_counter: _ParseCounter,
) -> None:
    """@brief The opt-out flag disables the sidecar entirely.

    @version 2
    """
    default_cache = tmp_path / "cold.db.idxcache"
    parse_counter.paths.clear()
    _build(guard_repo, tmp_path / "cold.db", no_cache=True)
    full_parses = len(parse_counter.paths)

    assert not default_cache.exists()
    assert full_parses > 0

    parse_counter.paths.clear()
    _build(guard_repo, tmp_path / "warm.db", no_cache=True)
    assert len(parse_counter.paths) == full_parses


## @brief A cached build's graph output must equal a no-cache build's.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @return None.
## @version 3
def test_cache_output_matches_no_cache(guard_repo: Path, tmp_path: Path) -> None:
    """The cache must ACCELERATE, never ALTER: a cached build and a no-cache
    build must produce identical tables. `test_warm_rebuild_is_deterministic`
    only compares warm-vs-warm (both cached), so a cache bug that systematically
    changes the graph while staying internally consistent would pass it — this
    guards cache-vs-no-cache. `meta` is excluded: it carries the wall-clock
    doxygen generation timestamp, which legitimately differs between two
    independent doxygen runs (the graph tables, which matter, must not).

    `build_meta`'s `refresh.*` cost namespace is excluded for the same class of
    reason and asserted separately — see `_BUILD_COST_PREFIX`. The two arms expect
    DIFFERENT key sets here, and that asymmetry is itself the assertion: a build with
    no cache must not claim a cache score, because "zero files taken from cache" and
    "there was no cache" are different facts.

    @brief Cached graph output equals no-cache output (excluding wall-clock rows).
    @version 3
    """
    cache = tmp_path / "shared.idxcache"
    nocache = _dump(_build(guard_repo, tmp_path / "nc.db", no_cache=True))
    cached = _dump(_build(guard_repo, tmp_path / "ca.db", cache=cache))
    assert _strip_build_cost(nocache) == _BUILD_COST_KEYS_ALWAYS
    assert _strip_build_cost(cached) == _BUILD_COST_KEYS
    nocache.pop("meta", None)
    cached.pop("meta", None)
    assert {t: len(r) for t, r in nocache.items()} == {t: len(r) for t, r in cached.items()}
    assert nocache == cached


## @brief --rebuild ignores cached entries but re-warms them.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @param parse_counter Installed per-file parse recorder.
## @return None.
## @version 2
def test_rebuild_forces_full_work_then_rewarms(
    guard_repo: Path,
    tmp_path: Path,
    parse_counter: _ParseCounter,
) -> None:
    """@brief A forced rebuild re-parses everything and refreshes the cache.

    @version 2
    """
    cache = tmp_path / "shared.idxcache"
    _build(guard_repo, tmp_path / "cold.db", cache=cache)
    cold_parses = len(parse_counter.paths)

    parse_counter.paths.clear()
    _build(guard_repo, tmp_path / "forced.db", cache=cache, rebuild=True)
    assert len(parse_counter.paths) == cold_parses

    parse_counter.paths.clear()
    _build(guard_repo, tmp_path / "warm.db", cache=cache)
    assert parse_counter.paths == []


## @brief The default sidecar path is <output>.idxcache.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @return None.
## @version 2
def test_default_cache_path_is_beside_output(guard_repo: Path, tmp_path: Path) -> None:
    """@brief Without --index-cache the sidecar lands beside the database.

    @version 2
    """
    _build(guard_repo, tmp_path / "clew.db")
    assert (tmp_path / "clew.db.idxcache").exists()


## @brief A CLEW_BUILD_VERSION change wipes the whole cache.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @return None.
## @version 2
def test_build_version_change_wipes_cache(guard_repo: Path, tmp_path: Path) -> None:
    """Belt-and-braces invalidation: a pipeline-logic bump must not leave any
    stage serving payloads produced by the old logic.

    @brief Build-version bump drops every cached entry.
    @version 2
    """
    cache_path = tmp_path / "shared.idxcache"
    _build(guard_repo, tmp_path / "cold.db", cache=cache_path)
    assert _stage_rows(cache_path)

    conn = sqlite3.connect(str(cache_path))
    conn.execute("UPDATE cache_meta SET value = '-1' WHERE key = 'build_version'")
    conn.commit()
    conn.close()

    reopened = IndexCache(cache_path, guard_repo)
    try:
        assert _stage_rows(cache_path) == {}
    finally:
        reopened.close()
