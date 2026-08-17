# SPDX-License-Identifier: MIT
"""Index THIS checkout with the real pipeline and assert the graph is non-trivial.

**Needs no network** — the target is ourselves, so the only environment problem
that can reach it is a missing `doxygen`.

    pytest tests/integration/test_self_index.py --integration

**Every threshold here is an ORDER-OF-MAGNITUDE FLOOR, not a pin.** This tree
changes daily; an exact count would be a maintenance tax that buys no safety,
and the failure it needs to catch is "a whole extraction layer went silent",
which is a collapse to zero, not a drift of ten. The floors were set at roughly
half of a measurement taken while writing this file (2016 memberdef / 1257
functions / 2024 ast / 1139 ast_member / 839 doxygen_sqlite /
102 files / 7 threads), so shrinking the project by half is allowed and
silencing a layer is not. Re-measured 2026-08-11 for gh#362: 3997 memberdef /
2416 functions / 2620 ast / **0 ast_member** / 1623 doxygen_sqlite / 246 files /
8 threads — every floor still cleared except `ast_member`, whose zero is
DELIBERATE and is explained at `AST_MEMBER_IS_STRUCTURALLY_ZERO_ON_PYTHON`.

@brief Real-pipeline self-index counts and layer-liveness floors.
@version 4
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from tree_sitter import Language, Parser
from tree_sitter_python import language as py_language

from clew.call_edges import SOURCE_AST_MEMBER, _ast_harvest_calls

pytestmark = pytest.mark.integration

## Floors per `call_edges.source`. Each key is a layer that MUST contribute on a
## Python codebase; a zero here means that extractor stopped working, which is
## the failure this file exists to catch.
##
## `ast_member` WAS A KEY HERE AT A FLOOR OF 400 AND IS DELIBERATELY GONE — see
## `AST_MEMBER_IS_STRUCTURALLY_ZERO_ON_PYTHON`. `binding` (23) and `fnptr` (2) are
## measured but NOT floored: both come from a handful of fixture files, so a floor
## over them would report a fixture edit as an extractor failure.
CALL_EDGE_FLOORS = {
    "ast": 1000,
    "doxygen_sqlite": 400,
}

## WHY `ast_member` IS ZERO ON THIS INDEX, and why that is not a silent layer.
##
## gh#347 made an unresolved call produce NO ROW, and gh#26's demotion before it made
## a unique NAME insufficient evidence for a member call. An `ast_member` edge can now
## earn a row on exactly ONE path: the call site WROTE a qualifier
## (`Ns::Class::method()`), and narrowing the same-named candidates by it leaves
## exactly one. Python has no such syntax — `obj.method()` names a RECEIVER, not a
## type — so `pyast.harvest_calls` emits three-element sites with no qualifier field
## at all, `_ast_record_call_edge` sees `qualified=''`, and `unverified_receiver` is
## true for every one of them. Zero is the only possible count on a Python-only index.
##
## PROVEN RATHER THAN ASSUMED (gh#362), because zero is also what a broken harvest
## looks like and gh#358 had just rewritten how harvesting is driven. Three checks:
## the non-member `ast` layer is unaffected (2620 rows, floor 1000); the walker still
## FINDS 2521 `ast_member` call sites in `clew/` alone, so nothing stopped
## harvesting; and the sites it finds are `append`, `reset` — `list.append` is a
## stdlib method, and a name-keyed edge from it to some indexed `append` is precisely
## the fabrication gh#347 removed.
##
## The floor is NOT re-derived to 0, because a floor of zero asserts nothing. It is
## replaced by `test_ast_member_is_zero_by_rule_not_by_a_broken_harvest`, which pins
## the rule in BOTH directions: no rows AND a live harvest. A Python target losing
## `ast_member` rows is correct; losing `ast_member` SITES is a regression.
AST_MEMBER_IS_STRUCTURALLY_ZERO_ON_PYTHON = 0

## Floor for indexed function rows.
MIN_FUNCTIONS = 800

## Floor for total memberdef rows (functions plus variables/typedefs/classes).
MIN_MEMBERDEFS = 1000

## Floor for indexed files. The scope is the WHOLE repository — this repo declares no
## `index_scope`, and gh#333 made "declaration > whole repo" the precedence, so the
## older note here naming a guard-declared `^(clew|scripts|tests)/.*\\.py$`
## pattern described a scope that no longer applies. 40 is well under the measured 246.
MIN_FILES = 40


## @brief One scalar COUNT(*) from a database.
## @param db Database to read.
## @param sql A query returning a single count.
## @param params Query parameters.
## @return The count.
## @version 1
def _count(db: Path, sql: str, params: tuple = ()) -> int:
    """@brief Run one counting query.

    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


## @brief Row counts per `call_edges.source`.
## @param db Database to read.
## @return Mapping of provenance layer to its row count.
## @version 1
def _edges_by_source(db: Path) -> dict[str, int]:
    """@brief Group call_edges by the layer that produced them.

    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return dict(conn.execute("SELECT source, COUNT(*) FROM call_edges GROUP BY source"))
    finally:
        conn.close()


## @brief The self index carries a non-trivial node and edge graph.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 2
def test_self_index_produces_a_non_trivial_graph(self_index_db: Path) -> None:
    """Nodes, files, and every call-edge layer above its floor.

    The per-layer breakdown is the point: a single total would stay comfortably
    above any floor while one of the four extractors produced nothing, and the
    layers are separately meaningful (`ast_member` in particular exists to keep
    the mostly-fuzzy member-access edges distinguishable from `ast`).

    @brief Self-index node/edge counts clear their floors.
    @version 2
    """
    assert _count(self_index_db, "SELECT COUNT(*) FROM memberdef") >= MIN_MEMBERDEFS
    functions = _count(self_index_db, "SELECT COUNT(*) FROM memberdef WHERE kind = 'function'")
    assert functions >= MIN_FUNCTIONS
    assert _count(self_index_db, "SELECT COUNT(*) FROM path") >= MIN_FILES

    observed = _edges_by_source(self_index_db)
    below = {
        source: (observed.get(source, 0), floor)
        for source, floor in CALL_EDGE_FLOORS.items()
        if observed.get(source, 0) < floor
    }
    assert below == {}, f"call_edges layers below their floor (observed, floor): {below}"

    # Reachability ran and covered EVERY function. One row per function is the
    # pass's contract; a partial pass would leave the query layer unable to say
    # whether a symbol is live or simply unvisited.
    assert _count(self_index_db, "SELECT COUNT(*) FROM symbol_liveness") == functions


## @brief `ast_member` is empty by the resolution rule, not by a dead harvest.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_ast_member_is_zero_by_rule_not_by_a_broken_harvest(self_index_db: Path) -> None:
    """THE REPLACEMENT FOR A FLOOR OF 400 (gh#362), and the whole reason it is not a
    floor of 0: an empty layer has two indistinguishable causes, and only one of them
    is correct. This asserts BOTH halves of the correct one.

    * NO ROWS — because gh#347 refuses to key an edge on a name. A row appearing here
      on a Python target means an unqualified member call started being resolved
      again, which is the fabrication that measured 2.9% precision on a public C++
      target while reporting `confidence='resolved'`.
    * A LIVE HARVEST — because the walker must still be FINDING those call sites. If
      this half ever fails while the first half passes, the layer is empty for the
      wrong reason and every count on a C++ target is understated too.

    The second half re-parses this repo's own package rather than reading the
    database, deliberately: the sites are dropped at resolution, so nothing about them
    survives into a table, and a database-side proxy for "the harvest works" does not
    exist.

    @brief No `ast_member` rows, and a harvest that still finds `ast_member` sites.
    @version 1
    """
    observed = _edges_by_source(self_index_db)
    assert observed.get(SOURCE_AST_MEMBER, 0) == AST_MEMBER_IS_STRUCTURALLY_ZERO_ON_PYTHON, (
        f"{observed.get(SOURCE_AST_MEMBER)} ast_member row(s) on a Python-only index. "
        "Python writes no call-site qualifier, so no member call can be verified — an "
        "edge here is keyed on a bare name, which gh#347 removed as fabrication."
    )

    parser = Parser(Language(py_language()))
    package = Path(__file__).resolve().parents[2] / "clew"
    sites = 0
    for source_file in sorted(package.rglob("*.py")):
        src = source_file.read_bytes()
        for site in _ast_harvest_calls(parser.parse(src), src):
            sites += int(len(site) > 2 and site[2] == SOURCE_AST_MEMBER)
    assert sites > 100, (
        f"only {sites} ast_member call site(s) harvested from {package.name}/ — the "
        "walker has stopped recognising member calls, so the empty ast_member layer is "
        "a BROKEN HARVEST rather than gh#347's resolution rule. Measured 2521 sites at "
        "the time this was written; the threshold is deliberately far below that, "
        "because the claim is 'the harvest is alive', not a count."
    )


## @brief Stored paths are repo-root-relative, disclosing no build-machine layout.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_self_index_stores_relative_paths_and_leaks_no_absolute_ones(
    self_index_db: Path,
) -> None:
    """A PRIVACY assertion, and the only place it can be made honestly.

    This repo ships no Doxyfile, so its own index is built through the #33
    SYNTHESIS path — and that path used to store ABSOLUTE paths: 112 of 112 rows,
    each carrying the builder's home directory. MCP publishes this column on every
    reply that names a file — a dossier's `file`, a search hit's, a caller row's —
    so anyone handed a shared db also received the build machine's directory layout.
    `list_files` was the example here until it was deleted; the exposure surface is
    the COLUMN and did not narrow by one tool leaving.

    The bug survived every existing test because it fails silently UPWARD:
    `Path(repo_root) / "/abs/p"` returns the absolute operand, so each downstream
    reader resolved the file correctly and nothing observably broke. Only the
    repo-supplied-Doxyfile path produced relative names, so the two build paths
    quietly disagreed about the meaning of a public column.

    Asserted HERE rather than as a unit test on `synthesize_doxyfile` because the
    unit test can only check that the Doxyfile DECLARES `STRIP_FROM_PATH`, which
    is a proxy for doxygen having honoured it. This reads the real column out of a
    real index, which is the actual claim.

    THE RESOLVE HALF IS NOW SCOPED BY `dg_unresolved` (gh#362). It used to require that
    EVERY stored name resolve from the repo root, and two deliberate changes made that
    false without weakening the privacy claim at all:

      * `fix_doxygen_paths` reduces a path that resolves OUTSIDE the repo root to its
        bare basename, precisely BECAUSE storing the absolute name is the disclosure
        this test exists to forbid. On this tree that is 5 rows — `pthread.h`,
        `stdint.h`, `stddef.h`, `stdio.h`, `string.h` — system headers reached because
        the index scope became the whole repository (gh#333) and now covers the C
        fixtures under `tests/data/`, which include them.
      * doxygen registers everything harvested out of a header it never opened against
        one SYNTHETIC bracketed marker row, `[generated]`. It is not a file and cannot
        resolve anywhere.

    Both are already flagged: the pipeline stamps `dg_unresolved = 1` on exactly those
    rows. So the assertion keys off that column instead of being relaxed — and it is
    STRONGER than what it replaces, because it now runs in both directions. An
    unflagged row must resolve (a mangled repo path is still caught), AND a flagged row
    must NOT resolve (a real repo file cannot be quietly excused by mislabelling it).
    The absolute-path ban is untouched and applies to every row regardless of flag,
    which is the privacy claim itself.

    @brief No stored path is absolute, and every unflagged one resolves.
    @version 2
    """
    conn = sqlite3.connect(str(self_index_db))
    try:
        rows = [(row[0], row[1]) for row in conn.execute("SELECT name, dg_unresolved FROM path")]
    finally:
        conn.close()

    names = [name for name, _ in rows]
    assert names, "precondition: the index must have indexed some files"
    absolute = [n for n in names if n.startswith("/")]
    assert absolute == [], (
        f"{len(absolute)} of {len(names)} stored paths are absolute and disclose the "
        f"build machine's layout, e.g. {absolute[:3]}"
    )

    # Relative is only meaningful if the paths still RESOLVE from the repo root. A test
    # that merely banned a leading slash would pass on mangled names.
    repo_root = Path(__file__).resolve().parents[2]
    missing = [n for n, flag in rows if not flag and not (repo_root / n).exists()]
    assert missing == [], (
        f"stored paths that neither resolve from the repo root nor carry "
        f"dg_unresolved: {missing[:3]}"
    )
    # The other direction, which is what stops the line above from becoming a licence
    # to flag anything inconvenient: a row claiming to be unresolvable must actually be
    # unresolvable. Without this, one mislabelled row would silently leave the resolve
    # check with nothing to say about it.
    mislabelled = [n for n, flag in rows if flag and (repo_root / n).exists()]
    assert mislabelled == [], (
        f"paths flagged dg_unresolved that DO resolve from the repo root: "
        f"{mislabelled[:3]} — a real repo file is being excused as external"
    )


## @brief The thread layer populates and resolves its entry points.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_self_index_thread_layer_resolves_its_entries(self_index_db: Path) -> None:
    """A separate claim from the counts, so a separate test.

    The floor is 1, not the 7 measured: every one of those rows comes from the
    `tests/data/pysample/` spawn fixtures, which the guard-declared index scope
    legitimately covers, and pinning a fixture-derived count would make editing
    those fixtures look like a regression. What is worth asserting is that the
    layer produced rows AND resolved each thread's entry to a real function —
    an unresolved entry is a NULL rowid, and the vocabulary CHECKs already
    refuse a bad `kind`/`source`/`confidence` at insert time, so re-asserting
    those in Python would test SQLite rather than the extractor.

    @brief Threads exist and every entry resolves to an indexed function.
    @version 1
    """
    assert _count(self_index_db, "SELECT COUNT(*) FROM threads") >= 1
    assert _count(self_index_db, "SELECT COUNT(*) FROM thread_membership") >= 1

    # A NULL entry rowid is CORRECT for an entry that is not a function of this
    # repo, and the original form of this assertion (`unresolved == 0`) forbade
    # exactly that — so it failed the moment a test fixture spawned a thread on a
    # STDLIB method. On this tree that is real: `threading.Thread(
    # target=httpd.serve_forever)` and `target=httpd.shutdown` in the viewer's test
    # fixture name `http.server` methods, which cannot resolve here.
    #
    # Leaving them NULL is the documented fail-closed behaviour — CLAUDE.md: "a
    # qualified entry that doesn't resolve to its own class stays NULL, never
    # borrows another class's rowid" — and borrowing a same-named stranger's rowid
    # would be the actual bug, silently attributing a thread to unrelated code.
    #
    # So the falsifiable invariant is not "nothing is NULL", it is: an entry is NULL
    # ONLY when its own tail name is genuinely absent from the index. A NULL beside
    # a name the index DOES know is a resolution failure worth catching.
    conn = sqlite3.connect(str(self_index_db))
    try:
        unresolved = [
            row[0]
            for row in conn.execute(
                "SELECT t.name FROM threads t LEFT JOIN memberdef m "
                "ON m.rowid = t.entry_memberdef_rowid AND m.kind = 'function' "
                "WHERE m.rowid IS NULL"
            )
        ]
        indexed = {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind='function'")}
    finally:
        conn.close()

    wrongly_unresolved = [name for name in unresolved if name.rsplit(".", 1)[-1] in indexed]
    assert wrongly_unresolved == [], (
        f"thread entries left NULL although the index knows the function: "
        f"{wrongly_unresolved} — that is a resolution failure, not fail-closed"
    )
