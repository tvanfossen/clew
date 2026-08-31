# SPDX-License-Identifier: MIT
"""gh#358 — one parse per file, ten stages, ten independent cache keys.

The defect these tests pin is not a wrong row, it is a redundant one: `run_harvest`
built a fresh `parser_cache` per call and that cache holds tree-sitter *Parser*
objects, not parsed trees, so ten stages meant ten parses of every file. Counting
PARSES is therefore the whole point, and every assertion here counts them by
patching `harvest._ast_parse_one_file` — the same seam the integration tier uses.

The other half is what must NOT change: each stage keeps its own
`(content_sha, stage, stage_version, extra_key)` row, so invalidating one stage
recomputes one stage. A combined key would pass a "cold build parses once" test
and fail this one, which is why both live here.

@brief Tests for the shared per-file parse pass and its per-stage cache keys.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from clew import harvest
from clew.harvest import Harvester, run_harvest, run_shared_parse, try_import_tree_sitter
from clew.indexcache import IndexCache

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the shared parse pass needs tree_sitter + its C grammar",
)

## Three trivial C files. Content differs so each has its own content sha; two of
## them define a function so a payload is non-empty, and one is deliberately empty
## of functions so an empty payload is exercised too (an empty payload is a VALUE,
## not a miss — conflating the two would re-parse it on every build).
_FILES = {
    "a.c": "int a(void) { return 1; }\n",
    "b.c": "int b(void) { return a(); }\n",
    "c.c": "/* no functions here */\n",
}


## @brief A counting stand-in for the module's per-file parse entry point.
## @version 1
class _ParseCounter:
    """Records every path handed to the real parse function, then delegates.

    A LIST rather than a set: the bug is repeated work on the SAME file, so
    multiplicity is the measurement and deduplicating would erase it.

    @brief Parse-call recorder.
    @version 1
    """

    ## @brief Capture the original parse function.
    ## @version 1
    def __init__(self) -> None:
        self.paths: list[str] = []
        self._original = harvest._ast_parse_one_file

    ## @brief Record the path, then parse.
    ## @return Whatever the wrapped parse function returns.
    ## @version 1
    def __call__(self, rel_path: str, *args: Any, **kwargs: Any):
        self.paths.append(rel_path)
        return self._original(rel_path, *args, **kwargs)


## @brief A harvester recording nothing but the number of lines it saw.
## @version 1
class _CountingHarvester(Harvester):
    """Its payload is deliberately trivial — this suite is about how OFTEN the
    parse happens, not about what any stage extracts.

    @brief Test double for one cacheable stage.
    @version 1
    """

    ## @brief Name the stage and its version.
    ## @param stage Cache stage tag.
    ## @param stage_version Extraction version.
    ## @param extra_key Manifest-derived key component.
    ## @version 1
    def __init__(self, stage: str, stage_version: int = 1, extra_key: str = "") -> None:
        super().__init__(extra_key)
        self.stage = stage
        self.stage_version = stage_version
        self.label = stage
        self.harvested: list[int] = []

    ## @brief Harvest one file's (trivial) payload.
    ## @param tree Parsed tree.
    ## @param src_bytes Raw bytes.
    ## @return The file's byte length, as a one-element list.
    ## @version 1
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        self.harvested.append(len(src_bytes))
        return [len(src_bytes)]


## @brief A repo of three C files plus a database whose `path` table names them.
## @param tmp_path Per-test temp directory.
## @return (repo_root, db_path, cache_path).
## @version 1
@pytest.fixture
def indexed_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The `path` table is all `run_harvest`/`run_shared_parse` read from the index,
    so the fixture builds exactly that rather than a whole doxygen schema.

    @brief Minimal indexed repository.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, text in _FILES.items():
        (repo / name).write_text(text)
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE path (name TEXT)")
    conn.executemany("INSERT INTO path(name) VALUES (?)", [(n,) for n in sorted(_FILES)])
    conn.commit()
    conn.close()
    return repo, db, tmp_path / "idx.idxcache"


## @brief Build the four harvesters and the cache one test run shares.
## @param repo Repository root.
## @param cache_path Sidecar cache path.
## @return (cache, harvesters).
## @version 1
def _fixture_stages(repo: Path, cache_path: Path) -> tuple[IndexCache, list[Harvester]]:
    """@brief Four stages over one cache, standing in for the pipeline's ten.

    @version 1
    """
    cache = IndexCache(cache_path, repo)
    stages = [_CountingHarvester(f"probe_{n}") for n in range(4)]
    return cache, list(stages)


## @brief The shared pass parses each file once, whatever the stage count.
## @param indexed_repo The three-file fixture.
## @param monkeypatch pytest's attribute patcher.
## @return None.
## @version 1
def test_shared_pass_parses_each_file_once(
    indexed_repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE gh#358 ASSERTION. Four stages over three files: three parses, twelve
    payloads. Before the shared pass the same work cost twelve parses, and the
    ratio is the whole saving — so this counts BOTH, because "3 parses" alone would
    also be satisfied by a pass that quietly dropped a stage.

    @brief One parse per file, one payload per (file, stage).
    @version 1
    """
    repo, db, cache_path = indexed_repo
    counter = _ParseCounter()
    monkeypatch.setattr(harvest, "_ast_parse_one_file", counter)
    cache, stages = _fixture_stages(repo, cache_path)

    conn = sqlite3.connect(str(db))
    tally = run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)
    conn.close()

    assert len(counter.paths) == len(_FILES)
    assert sorted(counter.paths) == sorted(_FILES)
    assert tally.parsed == len(_FILES)
    assert tally.computed == len(_FILES) * len(stages)
    assert tally.cached == 0
    assert [len(s.harvested) for s in stages] == [len(_FILES)] * len(stages)


## @brief After the shared pass, every stage's own harvest parses nothing.
## @param indexed_repo The three-file fixture.
## @param monkeypatch pytest's attribute patcher.
## @return None.
## @version 1
def test_stages_after_shared_pass_do_not_parse(
    indexed_repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The saving only lands if the stages then find their rows. A stage whose key
    disagreed with the warmed one would re-parse and still produce correct rows —
    silently costing exactly what gh#358 set out to remove — so this asserts the
    ZERO, and asserts the payloads still arrive.

    @brief Warmed stages serve from cache and parse nothing.
    @version 1
    """
    repo, db, cache_path = indexed_repo
    cache, stages = _fixture_stages(repo, cache_path)
    conn = sqlite3.connect(str(db))
    run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)

    counter = _ParseCounter()
    monkeypatch.setattr(harvest, "_ast_parse_one_file", counter)
    for stage in stages:
        results = run_harvest(conn, repo, stage, try_import_tree_sitter(), cache)
        assert len(results) == len(_FILES)
    conn.close()

    assert counter.paths == []


## @brief Bumping ONE stage's version recomputes ONE stage.
## @param indexed_repo The three-file fixture.
## @param monkeypatch pytest's attribute patcher.
## @return None.
## @version 1
def test_one_stage_version_bump_recomputes_only_that_stage(
    indexed_repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE CONTROL THAT FORBIDS A COMBINED CACHE KEY. Sharing the parse is only safe
    while the KEYS stay separate: a merged key would either invalidate all four
    stages here (all-or-nothing) or serve a stale slice for the bumped one (lossy).
    Either shows up as a `computed` count that is not exactly one stage's worth.

    @brief One invalidated stage costs one stage's recomputation.
    @version 1
    """
    repo, db, cache_path = indexed_repo
    cache, stages = _fixture_stages(repo, cache_path)
    conn = sqlite3.connect(str(db))
    run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)

    stages[1].stage_version += 1
    counter = _ParseCounter()
    monkeypatch.setattr(harvest, "_ast_parse_one_file", counter)
    tally = run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)
    conn.close()

    # Each file is still parsed at most once, and only the bumped stage recomputes.
    assert len(counter.paths) == len(_FILES)
    assert tally.computed == len(_FILES)
    assert tally.cached == len(_FILES) * (len(stages) - 1)
    # The superseded rows are left alone: invalidation is by KEY, not by deletion.
    rows = cache.conn.execute(
        "SELECT stage, stage_version, COUNT(*) FROM extract_cache "
        "GROUP BY stage, stage_version ORDER BY stage, stage_version",
    ).fetchall()
    assert (stages[1].stage, stages[1].stage_version, len(_FILES)) in rows
    assert (stages[1].stage, stages[1].stage_version - 1, len(_FILES)) in rows


## @brief An unchanged tree parses nothing at all on the next build.
## @param indexed_repo The three-file fixture.
## @param monkeypatch pytest's attribute patcher.
## @return None.
## @version 1
def test_unchanged_tree_parses_nothing(
    indexed_repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared pass must not make an incremental refresh worse. It asks
    `extract_has` per (file, stage) and parses only when at least one misses, so a
    fully-cached tree costs existence checks and no parse — and no payload DECODE
    either, which is why `extract_has` exists rather than reusing `extract_get`.

    @brief A warm refresh does no parsing.
    @version 1
    """
    repo, db, cache_path = indexed_repo
    cache, stages = _fixture_stages(repo, cache_path)
    conn = sqlite3.connect(str(db))
    run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)

    counter = _ParseCounter()
    monkeypatch.setattr(harvest, "_ast_parse_one_file", counter)
    tally = run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)
    conn.close()

    assert counter.paths == []
    assert tally.parsed == 0
    assert tally.computed == 0
    assert tally.cached == len(_FILES) * len(stages)


## @brief --rebuild recomputes everything, but each file only once.
## @param indexed_repo The three-file fixture.
## @param monkeypatch pytest's attribute patcher.
## @return None.
## @version 1
def test_rebuild_still_parses_each_file_once(
    indexed_repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--rebuild` sets `read_enabled=False` so nothing on disk is trusted. Without
    the this-run exemption in `IndexCache._readable`, the shared pass would compute
    every payload and every stage would then MISS and parse again — `--rebuild`
    would be the one mode gh#358 did not fix, and nothing would say so.

    @brief A forced rebuild reuses its own recomputation.
    @version 1
    """
    repo, db, cache_path = indexed_repo
    warm, stages = _fixture_stages(repo, cache_path)
    conn = sqlite3.connect(str(db))
    run_shared_parse(conn, repo, stages, try_import_tree_sitter(), warm)
    warm.conn.commit()

    rebuild = IndexCache(cache_path, repo, read_enabled=False)
    fresh = [_CountingHarvester(f"probe_{n}") for n in range(4)]
    counter = _ParseCounter()
    monkeypatch.setattr(harvest, "_ast_parse_one_file", counter)
    tally = run_shared_parse(conn, repo, fresh, try_import_tree_sitter(), rebuild)
    for stage in fresh:
        assert len(run_harvest(conn, repo, stage, try_import_tree_sitter(), rebuild)) == len(_FILES)
    conn.close()

    # Everything was recomputed (nothing on disk was trusted) …
    assert tally.computed == len(_FILES) * len(fresh)
    assert tally.cached == 0
    # … and yet each file was parsed exactly once, not once per stage.
    assert len(counter.paths) == len(_FILES)


## @brief One (file, stage) payload is counted once, not once per consumer.
## @param indexed_repo The three-file fixture.
## @return None.
## @version 1
def test_pair_accounting_is_not_double_counted(
    indexed_repo: tuple[Path, Path, Path],
) -> None:
    """`misses` is published as the index's `payloads_recomputed` and `status` shows it
    to an agent deciding whether to trust an answer. Since the shared pass COMPUTES
    what the stages then READ, naive counting would report a fully cold build as
    fully missed AND fully hit at the same time.

    @brief A cold build reports misses only; a warm one reports hits only.
    @version 1
    """
    repo, db, cache_path = indexed_repo
    cache, stages = _fixture_stages(repo, cache_path)
    conn = sqlite3.connect(str(db))
    run_shared_parse(conn, repo, stages, try_import_tree_sitter(), cache)
    for stage in stages:
        run_harvest(conn, repo, stage, try_import_tree_sitter(), cache)
    assert (cache.hits, cache.misses) == (0, len(_FILES) * len(stages))
    cache.conn.commit()

    warm = IndexCache(cache_path, repo)
    run_shared_parse(conn, repo, stages, try_import_tree_sitter(), warm)
    for stage in stages:
        run_harvest(conn, repo, stage, try_import_tree_sitter(), warm)
    conn.close()
    assert (warm.hits, warm.misses) == (len(_FILES) * len(stages), 0)


## Stages the plan holds as OPTIONAL fields, present only when a manifest declares them. They are
## still plan-managed — which is the property under test — so the check below requires them to be
## FIELDS of `HarvestPlan` rather than instances in a plan built without their declarations.
_CONDITIONAL_STAGES = {"dispatch", "mqtt"}


## @brief Every harvester the codebase defines is one the shared pass warms.
## @return None.
## @version 1
def test_every_harvester_subclass_is_reachable_from_the_plan() -> None:
    """THE GUARD THAT WOULD HAVE CAUGHT `macro_refs`, AND THE REASON IT IS STRUCTURAL.

    `test_stages_after_shared_pass_do_not_parse` iterates a hand-built list, so a stage absent
    from that list is invisible to it — it passed for as long as `macro_refs` drove its own
    full-tree parse, costing 29.5 s of a 130 s cold build. A test that enumerates the thing it
    is checking cannot detect an omission FROM that thing.

    So this enumerates `Harvester.__subclasses__()` after importing the whole package: the
    codebase's own answer to "what harvesters exist", which no plan edit can shrink. A new
    harvester that forgets the plan fails here on the day it is written, with a message naming
    the cost of not fixing it.

    @brief No harvester runs outside the shared parse.
    @version 1
    """
    import importlib
    import pkgutil

    import clew
    from clew.harvest_plan import HarvestPlan, build_harvest_plan

    ## Subclasses only register once their module is imported, and the pipeline imports them
    ## lazily — so without this walk the set is whatever earlier tests happened to touch, and
    ## the assertion would silently weaken as import order changed.
    for mod in pkgutil.iter_modules(clew.__path__):
        importlib.import_module(f"clew.{mod.name}")

    ## SCOPED TO THE PACKAGE. `__subclasses__()` sees every subclass alive in the interpreter,
    ## including this module's own `_CountingHarvester` test double — which carries the base
    ## class's empty `stage` and made the first run of this guard fail on `['']`. Filtering by
    ## `__module__` asks the question that was meant: what does *clew* define?
    defined = {
        cls.stage for cls in Harvester.__subclasses__() if cls.__module__.startswith("clew.")
    }
    warmed = {h.stage for h in build_harvest_plan().active()}
    fields = set(HarvestPlan.__dataclass_fields__)

    missing = defined - warmed - _CONDITIONAL_STAGES
    assert not missing, (
        f"harvester stage(s) {sorted(missing)} run outside the shared parse, so each one "
        "re-parses every indexed file — the defect that cost 29.5 s of a 130 s cold build "
        "when macro_refs did it. Add the harvester to HarvestPlan and to active()."
    )
    ## The conditional half: absent from a plan built with no manifests, but they must still be
    ## the PLAN's to construct. Named fields rather than instances, because that is the property
    ## that survives a build which declares nothing.
    assert {"dispatch", "subscribe"} <= fields
