# SPDX-License-Identifier: MIT
"""Tests for the central schema vocabulary (clew.vocabulary).

Three distinct jobs, and the first is the one that matters most:

  1. A FILESYSTEM SOURCE SCAN forbidding a raw `CHECK(` literal anywhere in the
     package outside `vocabulary.py`. No artifact-based test can replace it: a
     hand-rolled CHECK inside a CREATE TABLE that the fixture build never
     executes is invisible to any reconcile against a shipped database
     (`enrichment.architecture_topics` is created only under `--enrich` and
     exists in none of the databases on this machine). It scans via
     `pathlib.rglob`, NOT `git ls-files`, because the gate is blind to untracked
     files — that is exactly how `htmlview.py` once landed 10 violations after a
     green run.

  2. A COMMITTED GOLDEN SNAPSHOT (`tests/data/schema_vocabulary.json`) compared
     against a freshly built schema. Comparing the shipped CHECK to the registry
     that GENERATED it passes by construction for any value set, so widening a
     vocabulary would be undetectable. The snapshot is an external baseline a
     human has to deliberately edit.

  3. GENERATOR EDGE CASES that the idiom this replaces got wrong — a one-value
     vocabulary, an apostrophe-bearing value, and byte-stability across
     interpreter processes with different hash seeds.

@brief Vocabulary registry, generated-CHECK, and source-scan tests.
@version 1
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from schema_snapshot import parse_checks

from clew.ast_symbols import ensure_symbol_provenance
from clew.call_edges import build_call_edges
from clew.callback_edges import _ensure_external_boundaries_table
from clew.datamodel import _ensure_table as _ensure_data_model_keys_table
from clew.kconfig import ensure_kconfig_tables
from clew.kconfig_gates import ensure_kconfig_gates_table
from clew.locks import _ensure_lock_tables
from clew.reachability import mark_reachability
from clew.requirements import _create_req_edges_table
from clew.shared_key_edges import _ensure_shared_key_edges_table
from clew.threads import _ensure_threads_tables
from clew.vocabulary import (
    ACQ_STRENGTH,
    BOOL_COLUMNS,
    BOUNDARY_KIND,
    BOUNDARY_SOURCE,
    BOUNDARY_STRENGTH,
    CALL_SOURCE,
    CALL_SOURCE_DECLARED_DISPATCH,
    COLUMNS,
    KEY_STRENGTH,
    LOCK_IDENTITY,
    THREAD_KIND,
    THREAD_STRENGTH,
    VOCABULARIES,
    DeclarationError,
    Vocabulary,
    bool_check,
    check,
)

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "clew"
SNAPSHOT = REPO / "tests" / "data" / "schema_vocabulary.json"


# ─── 1. source scans: the only thing that stops a future bypass ──────────────


## @brief Every .py file in the shipped package, found on the FILESYSTEM.
## @return Package sources, excluding compiled bytecode directories.
## @version 1
def _package_sources() -> list[Path]:
    """rglob, not `git ls-files`: the git-aware gate cannot see an untracked
    file, which is how a new module once landed 10 standards violations after a
    green `pre-commit --all-files` run.

    @brief Walk the package on disk, git state irrelevant.
    @version 1
    """
    return [p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_raw_check_literal_survives_outside_vocabulary() -> None:
    """The whole point of the module: `CHECK(` may appear in exactly ONE file.

    An artifact reconcile cannot catch a hand-rolled CHECK in a CREATE TABLE the
    fixture build never runs, and `pre-commit --all-files` cannot see a brand-new
    untracked file at all. This scan sees both.
    """
    offenders = [
        str(path.relative_to(REPO))
        for path in _package_sources()
        if path.name != "vocabulary.py" and "CHECK(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"raw CHECK( literal outside vocabulary.py in {offenders} — "
        "generate it with vocabulary.check(table, column) / bool_check(column)"
    )


def test_package_sources_were_actually_scanned() -> None:
    """A scan that finds no files passes vacuously. Pin that it walked the whole
    package including the two subpackages a `**` pathspec silently skips."""
    scanned = {p.relative_to(PACKAGE).as_posix() for p in _package_sources()}
    assert len(scanned) > 25
    assert "vocabulary.py" in scanned
    assert any(name.startswith("query/") for name in scanned)
    assert any(name.startswith("mcp_server/") for name in scanned)


def test_no_module_redefines_a_valid_constant() -> None:
    """`_VALID_KINDS` was defined TWICE with DIFFERENT values (a set of thread
    kinds in threads.py, a tuple of lock kinds in locks.py). Same name, same
    package, no relationship — a cross-import would have produced a silently
    wrong CHECK. After the migration no module defines any `_VALID_` constant,
    so the collision cannot be reintroduced by accident.

    Matches a module-level ASSIGNMENT, not the bare substring: prose mentioning
    the retired names (this module's own docstring does) is not a violation, and
    a scan that a docstring reflow can break is a scan people delete."""
    offenders = [
        str(path.relative_to(REPO))
        for path in _package_sources()
        if re.search(r"^_VALID_\w*\s*[:=]", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert offenders == [], (
        f"module-level _VALID_ constant reintroduced in {offenders} — "
        "the allowed values belong in vocabulary.py"
    )


def test_cache_stage_names_are_not_spelled_inline() -> None:
    """`extract_cache.stage` carries NO CHECK and is part of the cache PRIMARY
    KEY, so a typo never raises — it silently produces a permanent cache miss
    for that harvester. The six names come from vocabulary constants."""
    offenders = [
        f"{path.relative_to(REPO)}:{line}"
        for path in _package_sources()
        if path.name != "vocabulary.py"
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("stage = ") and '"' in line
    ]
    assert offenders == [], f"inline extract_cache stage literal in {offenders}"


# ─── 2. the shipped schema, against a committed external baseline ────────────


## @brief A database carrying every CHECK-bearing table, built by the real DDL.
## @version 1
@pytest.fixture
def schema_db(tmp_path: Path) -> Path:
    """Runs the pipeline's OWN table creators against a blank file, so the CHECK
    constraints under test are the ones a real build ships — not a copy.

    Only the doxygen-shaped tables those creators read from are hand-made
    (`memberdef` / `xrefs`), plus one non-fuzzy call edge so `mark_reachability`
    gets past its early-return and actually creates `symbol_liveness`.

    @brief Fresh database carrying every CHECK-constrained pipeline table.
    @version 1
    """
    db = tmp_path / "schema.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE memberdef (name TEXT, kind TEXT);
        CREATE TABLE xrefs (src_rowid INTEGER, dst_rowid INTEGER, context TEXT);
        INSERT INTO memberdef (name, kind) VALUES ('main', 'function');
        INSERT INTO memberdef (name, kind) VALUES ('helper', 'function');
        """
    )
    ## gh#11's CHECK is the ONE registered constraint on a table this package does
    ## not create, so it arrives by ALTER TABLE rather than from a CREATE TABLE the
    ## fixture could call. Applied through the shipping function for the same reason
    ## every other table here is: a hand-written copy of the DDL would pass this
    ## fixture's own tests while the real build shipped something else.
    ensure_symbol_provenance(conn)
    conn.commit()
    conn.close()

    build_call_edges(db)
    conn = sqlite3.connect(str(db))
    ## COLUMNS NAMED, not positional. A positional `VALUES` here broke the instant gh#350 added
    ## `via_macro_rowid`, and the failure was an arity error in a fixture rather than anything
    ## about the CHECK constraints this is here to exercise — a test that fails for a reason
    ## unrelated to its subject teaches the next reader to edit the count and move on.
    conn.execute(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (1, 2, 'doxygen_sqlite', 'exact')",
    )
    _ensure_lock_tables(conn)
    _ensure_threads_tables(conn)
    _ensure_shared_key_edges_table(conn)
    _ensure_external_boundaries_table(conn)
    ## gh#18. Two creators rather than one, because the Kconfig structure layer and the
    ## CONFIG-gating layer fail independently — a repo can have a parseable Kconfig and
    ## no C sources, or gated C and an unparseable Kconfig — and a shared creator would
    ## make one layer's absence look like the other's.
    ensure_kconfig_tables(conn)
    ensure_kconfig_gates_table(conn)
    _create_req_edges_table(conn)
    ## gh#351. Created unconditionally by its own stage — a target with no data model gets an
    ## empty table rather than none — so the fixture calls it unconditionally too.
    _ensure_data_model_keys_table(conn)
    conn.commit()
    conn.close()
    mark_reachability(db)
    return db


def test_shipped_schema_matches_the_committed_snapshot(schema_db: Path) -> None:
    """The golden baseline. Deliberately NOT compared against COLUMNS: a
    registry-vs-registry check passes for any value set, so widening a
    vocabulary would be invisible. Editing this JSON is a conscious act."""
    assert parse_checks(schema_db) == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_reconcile_is_bidirectional_and_unfiltered(schema_db: Path) -> None:
    """Both directions over EVERY table in sqlite_master, with no fixed list of
    pipeline tables — a hardcoded scope lets a tenth table escape even when it
    IS built. Safe unfiltered: doxygen's own tables carry zero CHECKs."""
    shipped = set(parse_checks(schema_db))
    registered = {f"{t}.{c}" for t, c in COLUMNS} | {f"{t}.{c}" for t, c in BOOL_COLUMNS}
    assert registered - shipped == set(), "registered but absent from the shipped schema"
    assert shipped - registered == set(), "shipped CHECK on a column no vocabulary claims"


def test_external_boundaries_source_carries_the_new_check(schema_db: Path) -> None:
    """`external_boundaries.source` was `TEXT NOT NULL DEFAULT 'callback_edges'`
    with nothing constraining it — unconstrained free text on a provenance
    column. Six of the nine CHECK-carrying tables use CREATE TABLE IF NOT
    EXISTS, so a tightened CHECK only lands because the CLI builds into a .tmp
    and os.replace()s it; this test fails the day an in-place refresh appears.

    Both stages that record a terminus are listed: `callback_edges` for the
    forwarded-fnptr kind and `declared_dispatch` for the declared interface
    boundary. A typo is still refused.
    """
    assert parse_checks(schema_db)["external_boundaries.source"] == [
        "callback_edges",
        "declared_dispatch",
    ]
    conn = sqlite3.connect(str(schema_db))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO external_boundaries "
            "(memberdef_rowid, global_name, kind, source, confidence) "
            "VALUES (1, 'g', 'unresolved_callback', 'typo', 'high')",
        )
    conn.close()


# ─── 3. the generator itself ─────────────────────────────────────────────────


def test_single_value_vocabulary_generates_valid_sql() -> None:
    """The idiom this replaces used `{tuple!r}`, which emits `IN ('x',)` for a
    one-value set — SQLite rejects the trailing comma. It survived only because
    every set it was applied to happened to have >= 2 values; `boundary_source`
    was the live one-value case until the declared-dispatch terminus widened it.

    So the case is exercised SYNTHETICALLY now, not through whichever registry
    entry happens to be short this week — the generator is what is under test,
    and binding the assertion to a real vocabulary made a legitimate widening
    look like a regression. Every registered one-value vocabulary is still
    checked, so the real case is covered the moment one exists again.
    """
    one = Vocabulary(id="one", values=("only",), means="test")
    assert one.check("c") == "CHECK(c IN ('only'))"
    conn = sqlite3.connect(":memory:")
    for vocab in [one, *(v for v in VOCABULARIES.values() if len(v.values) == 1)]:
        conn.execute(f"CREATE TABLE probe (c TEXT {vocab.check('c')})")
        conn.execute("INSERT INTO probe VALUES (?)", (vocab.values[0],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO probe VALUES ('__not_a_member__')")
        conn.execute("DROP TABLE probe")
    conn.close()


def test_the_declared_dispatch_provenance_is_separable_everywhere_it_lands() -> None:
    """A declared-dispatch edge exists because a manifest says an indirection
    connects two functions — no call site names it. A consumer must always be
    able to ask "would this edge exist without the manifest?", so the token is
    registered on BOTH surfaces the stage writes (`call_edges.source` and
    `external_boundaries.source`) and is spelled once."""
    assert CALL_SOURCE_DECLARED_DISPATCH == "declared_dispatch"
    assert CALL_SOURCE_DECLARED_DISPATCH in CALL_SOURCE
    assert CALL_SOURCE_DECLARED_DISPATCH in BOUNDARY_SOURCE
    # Ranked above doxygen's own exact xrefs: an author's statement of fact, not
    # a name match. Nothing consumes rank yet, so pin the intent here.
    assert CALL_SOURCE.rank[CALL_SOURCE_DECLARED_DISPATCH] > CALL_SOURCE.rank["doxygen_sqlite"]
    # A second terminus KIND, not a repair of the first — both must survive.
    assert "interface_boundary" in BOUNDARY_KIND
    assert "unresolved_callback" in BOUNDARY_KIND


def test_apostrophe_is_escaped_by_doubling() -> None:
    """`repr` quotes an apostrophe-bearing value with DOUBLE quotes, which
    SQLite reads as an identifier, not a string. No shipped value contains one
    today; the generator must not be the reason it can never be added."""
    vocab = Vocabulary(id="t", values=("it's", "plain"), means="test")
    assert vocab.check("c") == "CHECK(c IN ('it''s', 'plain'))"
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE t (c TEXT {vocab.check('c')})")
    conn.execute('INSERT INTO t VALUES ("it\'s")')
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO t VALUES ('nope')")
    conn.close()


def test_every_registry_value_satisfies_its_generated_check() -> None:
    """Round-trip: every registered value is accepted by the clause generated
    for it, and a non-member is rejected. Catches a registry that is a superset
    of what the SQL actually admits."""
    conn = sqlite3.connect(":memory:")
    for (table, column), vocab in COLUMNS.items():
        conn.execute(f"CREATE TABLE probe (c TEXT {vocab.check('c')})")
        for value in vocab.values:
            conn.execute("INSERT INTO probe VALUES (?)", (value,))
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            conn.execute("INSERT INTO probe VALUES ('__not_a_member__')")
        assert conn.execute("SELECT COUNT(*) FROM probe").fetchone()[0] == len(vocab.values), (
            f"{table}.{column} lost a value round-tripping"
        )
        conn.execute("DROP TABLE probe")
    conn.close()


def test_bool_check_admits_only_zero_and_one() -> None:
    """Booleans are ints with no vocabulary, so they get their own generator —
    `validated()` is meaningless for them."""
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE t (c INTEGER {bool_check('c')})")
    conn.execute("INSERT INTO t VALUES (0)")
    conn.execute("INSERT INTO t VALUES (1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO t VALUES (2)")
    conn.close()


def test_generated_clauses_are_stable_across_hash_seeds() -> None:
    """`values` is a tuple, never a set. A set's iteration order is not part of
    any contract, so generating from one (threads._VALID_KINDS WAS a set) would
    make the shipped schema text vary between builds for no visible reason."""
    runs = []
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        runs.append(
            subprocess.run(
                [sys.executable, str(REPO / "tests" / "vocab_dump.py")],
                capture_output=True,
                text=True,
                check=True,
                env=env,
            ).stdout
        )
    assert runs[0] == runs[1]
    # The literal is the point: it proves the emitted order follows the DECLARED
    # `values` tuple and not set/dict iteration, which PYTHONHASHSEED would
    # perturb between the two runs above. Updated deliberately when #58 added
    # `process`/`coroutine`, and again when the Windows spawn primitives added
    # `win32` — which sits right after `pthread` because that is where the
    # declared tuple puts it, and this assertion exists to prove exactly that.
    assert (
        "CHECK(kind IN ('task', 'pthread', 'win32', 'timer', 'isr', 'main', 'oneshot', "
        "'process', 'coroutine', 'unknown'))" in (runs[0])
    )


# ─── the registry's own invariants ───────────────────────────────────────────


def test_the_five_strength_vocabularies_are_distinct_objects() -> None:
    """Five columns share the tuple ('low','medium','high') and mean five
    different things — spawn-detection strength, inferred-vs-declared
    provenance, lock-identity certainty, acquisition-resolution success, and a
    constant on external_boundaries. One shared object would mean adding a value
    for ONE silently widens the CHECK on the other four, with every
    registry-vs-registry test still green."""
    five = [THREAD_STRENGTH, KEY_STRENGTH, LOCK_IDENTITY, ACQ_STRENGTH, BOUNDARY_STRENGTH]
    assert all(v.values == ("low", "medium", "high") for v in five)
    assert len({id(v) for v in five}) == 5
    assert len({v.id for v in five}) == 5
    assert len({v.means for v in five}) == 5


def test_rank_is_explicit_per_value_not_positional() -> None:
    """call_match is ordered strongest-first while every strength vocabulary is
    ordered weakest-first, so a positional ordinal inverts one of them — and the
    R4 dash map renders BOTH 'exact' and 'high' as solid. Rank is a dict."""
    call_match = VOCABULARIES["call_match"]
    assert call_match.values == ("exact", "resolved", "fuzzy")
    assert call_match.rank["exact"] > call_match.rank["fuzzy"]
    assert KEY_STRENGTH.values == ("low", "medium", "high")
    assert KEY_STRENGTH.rank["high"] > KEY_STRENGTH.rank["low"]


def test_every_registered_column_has_a_registered_vocabulary() -> None:
    """`check()` refuses an unregistered column instead of returning an empty
    string: a silently-absent CHECK is the hole this module exists to close."""
    for table, column in COLUMNS:
        assert check(table, column).startswith("CHECK(")
    with pytest.raises(KeyError):
        check("call_edges", "not_a_column")


def test_validated_returns_members_and_raises_on_anything_else() -> None:
    """The message must name the origin, the token and the full allowed set —
    that triple is what makes a fail-closed refusal cheaper to fix than a
    silent normalization."""
    assert THREAD_KIND.validated("pthread", owner="x", field="kind") == "pthread"
    with pytest.raises(DeclarationError) as exc:
        THREAD_KIND.validated("pthred", owner=".clew.yaml [thread_patterns]", field="kind")
    message = str(exc.value)
    assert ".clew.yaml [thread_patterns]" in message
    assert "'pthred'" in message
    # Spelled out in full, in declared order, and updated DELIBERATELY when the
    # vocabulary grows — #58 added `process`/`coroutine` for Python's spawn
    # primitives, and `win32` arrived with the Windows ones. The point of the
    # literal is that widening a fail-closed vocabulary is a decision someone has
    # to make on purpose, not a diff that slips through because the assertion was
    # derived from the thing it checks.
    assert "task, pthread, win32, timer, isr, main, oneshot, process, coroutine, unknown" in message


def test_reserved_values_are_check_allowed_but_written_by_nothing() -> None:
    """Reserved values keep the schema forward-compatible while telling a test
    asserting "every value is observed in data" which ones to exempt. They must
    still be real members, or the CHECK would reject a future writer."""
    for vocab in VOCABULARIES.values():
        assert vocab.reserved <= set(vocab.values), f"{vocab.id} reserves a non-member"
    # threads.py writes only 'medium'; 'low'/'high' exist for a future detector.
    assert THREAD_STRENGTH.reserved == frozenset({"low", "high"})
    # callback_edges.py writes only 'high' on a terminus row.
    assert BOUNDARY_STRENGTH.reserved == frozenset({"low", "medium"})
