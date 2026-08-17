# SPDX-License-Identifier: MIT
"""gh#37 — `candidates` made actionable: an ambiguous name is addressable, not just reported.

`models.Candidate` documented its `file` field as "the disambiguating hint a consumer passes
back" and there was nowhere to pass one. Every accessor took a bare name, `function_candidates`
matched `WHERE name=?`, and `identity_rowids` picked the definition-preferring first row — so
every other identity sharing a bare name was unreachable by any string a caller could supply.

WHAT THESE TESTS PIN, and why each one exists rather than being implied by the others:

  * The round trip closes — a `candidates[i].qualified` handed back selects THAT identity.
  * The bare path is untouched, so this is additive. Without that assertion the whole change
    could be a breaking one and every test above it would still pass.
  * `overridden_by` on a shared-name BASE, which is gh#37's motivating case: a virtual base
    shares its bare name with every override by construction, so the direction a consumer
    wants is exactly the one bare-name resolution cannot reach.
  * An unmatched selector returns NOTHING rather than falling back to the union. A
    disambiguator that silently widens is worse than none — the caller believes it narrowed.
  * `candidates` is still reported on a disambiguated call, so a narrowed answer stays
    distinguishable from a unique one.

@brief Tests for the gh#37 qualified-name disambiguator across the accessor surface.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import query as q
from clew.mcp_server.tools_query import QueryTools

## The fixture's three same-named identities. `harvest` is the real shape from this repo's own
## self-index — one base plus ten overrides, eleven memberdef rows all named `harvest` — reduced
## to a base and two overrides. Named constants because the point is which rowids are the SAME
## function and a bare integer does not say so.
##
## THE BASE DELIBERATELY DOES NOT HAVE THE LOWEST ROWID, and the first version of this fixture
## got that wrong and was caught by its own bare-name control. Resolution orders body rows
## first then by rowid, so putting the base at rowid 1 made the bare name find it and the
## fixture reproduced nothing. On the real self-index the base is `harvest.py`'s at rowid 10
## while `callback_edges.py`'s SUBCLASS is at rowid 9, so the bare name lands on an override —
## which has no overriders, hence the confident empty answer gh#37 measured.
OVERRIDE_A = 1
OVERRIDE_B = 2
BASE = 3
## A DECLARATION row of the base, sharing its qualified name. Present so the identity union is
## exercised: a selector that matched only one row would still pass every test without it.
BASE_DECL = 4

BASE_QUALIFIED = "pkg.harvest.Harvester.harvest"
A_QUALIFIED = "pkg.locks._LockHarvester.harvest"
B_QUALIFIED = "pkg.threads._SpawnHarvester.harvest"


## @brief An index with one base, two overrides and a decl row, all named `harvest`.
## @param tmp_path Per-test temporary directory.
## @return Path to the built clew.db.
## @version 1
@pytest.fixture()
def shared_name_db(tmp_path: Path) -> Path:
    """Models the case gh#37 is about: a name that denotes four rows and three identities,
    with the override relation recorded against the base's DECLARATION rowid so a
    rowid-keyed implementation cannot pass by accident (the same trap `test_overrides.py`
    sets, for the same reason).

    Call edges are planted per identity so `callers`/`callees` have something to narrow, and
    each override gets its own distinct caller — otherwise a query returning the union would
    be indistinguishable from one returning the right subset.

    @brief Seed a memberdef/call_edges/reimplements DB with three `harvest` identities.
    @return Path to a clew.db.
    @version 1
    """
    db = tmp_path / "shared.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT
        );
        CREATE TABLE reimplements (memberdef_rowid INTEGER, reimplemented_rowid INTEGER);
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, name) VALUES (?, ?)",
        [(1, "pkg/harvest.py"), (2, "pkg/locks.py"), (3, "pkg/threads.py"), (4, "pkg/harvest.pyi")],
    )
    ## (rowid, file_id, bodyfile_id, definition) — bodyfile_id == file_id marks a body row.
    rows = [
        (OVERRIDE_A, 2, 2, f"Any {A_QUALIFIED}"),
        (OVERRIDE_B, 3, 3, f"Any {B_QUALIFIED}"),
        (BASE, 1, 1, f"Any {BASE_QUALIFIED}"),
        (BASE_DECL, 4, 0, f"Any {BASE_QUALIFIED}"),
    ]
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', 'harvest', ?, ?, 10, 20, ?, '(self)', '', '', 0)",
        rows,
    )
    ## One distinct caller per identity, plus a caller of the base's DECLARATION row so the
    ## identity union is load-bearing on the edge side too.
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, 30, 40, ?, '()', '', '', 0)",
        [
            (10, "run_base", "Any pkg.driver.run_base"),
            (11, "run_a", "Any pkg.driver.run_a"),
            (12, "run_b", "Any pkg.driver.run_b"),
            (13, "run_decl", "Any pkg.driver.run_decl"),
        ],
    )
    conn.executemany(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) VALUES (?,?,?,?)",
        [
            (10, BASE, "doxygen_sqlite", "exact"),
            (13, BASE_DECL, "doxygen_sqlite", "exact"),
            (11, OVERRIDE_A, "doxygen_sqlite", "exact"),
            (12, OVERRIDE_B, "doxygen_sqlite", "exact"),
        ],
    )
    ## Recorded against the DECLARATION rowid, never the definition.
    conn.executemany(
        "INSERT INTO reimplements (memberdef_rowid, reimplemented_rowid) VALUES (?,?)",
        [(OVERRIDE_A, BASE_DECL), (OVERRIDE_B, BASE_DECL)],
    )
    conn.commit()
    conn.close()
    return db


## @brief A disambiguated resolve returns the ONE identity asked for.
## @param shared_name_db The three-identity index.
## @return None.
## @version 1
def test_a_qualified_selector_returns_the_one_identity_asked_for(shared_name_db: Path) -> None:
    """THE ROUND TRIP. Every one of the three identities must be reachable, including the two
    that are NOT the definition-preferring first row — those are the ones that were
    unreachable by any string before gh#37, and a test that only checked the first would pass
    against the old code.

    Asserted on `file` as well as `rowid`, because `rowid` alone would also be satisfied by an
    implementation that returned some arbitrary row of the right identity.
    """
    wanted = {
        BASE_QUALIFIED: ("pkg/harvest.py", BASE),
        A_QUALIFIED: ("pkg/locks.py", OVERRIDE_A),
        B_QUALIFIED: ("pkg/threads.py", OVERRIDE_B),
    }
    for qualified, (expect_file, expect_rowid) in wanted.items():
        ref = q.resolve_symbol(shared_name_db, "harvest", qualified)
        assert ref is not None, qualified
        assert ref.rowid == expect_rowid, qualified
        assert ref.file == expect_file, qualified


## @brief The bare-name path is unchanged, so the disambiguator is additive.
## @param shared_name_db The three-identity index.
## @return None.
## @version 1
def test_an_ambiguous_call_without_a_selector_behaves_as_before(shared_name_db: Path) -> None:
    """The control on the whole change. `qualified` must be OPTIONAL and omitting it must
    reproduce the previous behaviour exactly — the definition-preferring first row, with the
    alternatives listed in `candidates`. Without this assertion the change could be a breaking
    one and every other test here would still pass.

    Also pins that a bare call REMAINS ambiguous rather than being made to fail: the common
    case is a unique name, and forcing a selector on the ambiguous one would break callers to
    fix a case they mostly do not have.
    """
    ref = q.resolve_symbol(shared_name_db, "harvest")
    assert ref is not None
    assert ref.rowid == OVERRIDE_A, "the definition-preferring pick must not have moved"
    assert {c.qualified for c in ref.candidates} == {BASE_QUALIFIED, A_QUALIFIED, B_QUALIFIED}
    ## Every candidate carries the string that selects it — the field gh#37 added, and the
    ## reason the list is actionable rather than advisory.
    assert all(c.qualified for c in ref.candidates)


## @brief A disambiguated reply still discloses that the name is ambiguous.
## @param shared_name_db The three-identity index.
## @return None.
## @version 1
def test_a_disambiguated_reply_still_reports_the_alternatives(shared_name_db: Path) -> None:
    """Ambiguity is a property of the NAME, not of the call. Measuring `candidates` against
    the FILTERED rows would make every disambiguated reply look unique, so a consumer could
    not tell "this name has one meaning" from "I picked one of three" — and the second is the
    situation in which it most needs to know."""
    ref = q.resolve_symbol(shared_name_db, "harvest", A_QUALIFIED)
    assert ref is not None
    assert ref.rowid == OVERRIDE_A
    assert {c.qualified for c in ref.candidates} == {BASE_QUALIFIED, A_QUALIFIED, B_QUALIFIED}


## @brief An unmatched selector finds nothing; it never widens to the bare-name union.
## @param shared_name_db The three-identity index.
## @return None.
## @version 1
def test_an_unmatched_selector_returns_nothing_rather_than_the_union(
    shared_name_db: Path, tmp_path: Path
) -> None:
    """FAIL CLOSED. A selector that fell back to every same-named row on no match would be the
    worst available behaviour: the caller asked a narrow question, got a wide answer, and has
    no signal that the narrowing failed. A typo must read as "no such identity".

    Checked across the whole accessor surface rather than on one function, because a fallback
    would most likely be introduced in one place by someone making a single accessor
    "friendlier"."""
    bogus = "pkg.nowhere.NotAClass.harvest"
    assert q.resolve_symbol(shared_name_db, "harvest", bogus) is None
    assert q.dossier(shared_name_db, "harvest", bogus) is None
    assert q.callers(shared_name_db, "harvest", bogus) == []
    assert q.callees(shared_name_db, "harvest", bogus) == []
    assert q.overrides_of(shared_name_db, "harvest", bogus) == []
    assert q.overridden_by(shared_name_db, "harvest", bogus) == []
    assert q.source(shared_name_db, "harvest", tmp_path, qualified=bogus) is None


## @brief gh#37's motivating case: `overridden_by` on a base sharing its overrides' bare name.
## @param shared_name_db The three-identity index.
## @return None.
## @version 1
def test_overridden_by_reaches_a_base_whose_name_is_shared_with_its_overrides(
    shared_name_db: Path,
) -> None:
    """WHY gh#8 MADE gh#37 LOAD-BEARING. `override` MEANS sharing the base's name, so the
    direction a consumer actually wants — what runs when this virtual call dispatches — is
    precisely the direction bare-name resolution cannot reach. On this repo's own self-index
    the bare call returns ZERO while ten `reimplements` rows name the base.

    The bare assertion is half the test: without it this could pass on an implementation that
    ignored `qualified` and happened to resolve to the base."""
    assert q.overridden_by(shared_name_db, "harvest") == [], (
        "the bare name resolves to an OVERRIDE (lowest-rowid body row), and an override has "
        "no overriders -- so the pre-gh#37 answer is a confident, wrong empty list"
    )
    got = q.overridden_by(shared_name_db, "harvest", BASE_QUALIFIED)
    assert {ref.file for ref in got} == {"pkg/locks.py", "pkg/threads.py"}
    ## And the opposite direction, from an override up to its base.
    bases = q.overrides_of(shared_name_db, "harvest", A_QUALIFIED)
    assert [ref.file for ref in bases] == ["pkg/harvest.pyi"]


## @brief Neighbour lists narrow to the selected identity, decl rows included.
## @param shared_name_db The three-identity index.
## @return None.
## @version 1
def test_neighbour_lists_narrow_to_the_selected_identity(shared_name_db: Path) -> None:
    """The selector has to reach `identity_rowids`, not merely the identity lookup, or a
    disambiguated dossier would describe one function and list another's edges — which is the
    gh#26 defect gh#37 must not reintroduce in a new place.

    `run_decl` is the load-bearing row: it calls the base's DECLARATION, so a selector that
    narrowed to a single rowid instead of the identity's union would drop it."""
    assert {e.name for e in q.callers(shared_name_db, "harvest", BASE_QUALIFIED)} == {
        "run_base",
        "run_decl",
    }
    assert {e.name for e in q.callers(shared_name_db, "harvest", A_QUALIFIED)} == {"run_a"}
    assert {e.name for e in q.callers(shared_name_db, "harvest", B_QUALIFIED)} == {"run_b"}


## @brief The selector reaches the MCP wire, and a miss stays a miss there.
## @param shared_name_db The three-identity index.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_the_selector_reaches_the_mcp_tool_surface(shared_name_db: Path, tmp_path: Path) -> None:
    """gh#37's "done means" clause asks for a call REACHABLE FROM THE TOOL SURFACE that returns
    the implementors of a shared-name base. `overridden_by` is not itself a tool — it rides on
    `dossier` — so this is the assertion that the capability is reachable by a model and not
    only by the library.

    A bogus selector must produce the ordinary miss envelope rather than a widened answer, for
    the same reason the library-level test checks it: the wire is where a model's typo lands.

    KEYWORD, NOT POSITIONAL, since gh#372. `dossier`'s second positional slot is now `kind`,
    and `qualified` moved behind a bare `*` precisely so this call could not be silently
    reinterpreted — a selector read as a subject-kind filter is a wrong answer, where a
    TypeError is a caller-side fix."""
    tools = QueryTools(lambda: shared_name_db, lambda: tmp_path)

    bare = tools.dossier("harvest")
    assert bare["overridden_by"] == [], "the bare name reaches no override relation"

    with pytest.raises(TypeError):
        tools.dossier("harvest", BASE_QUALIFIED)  # type: ignore[misc]

    picked = tools.dossier("harvest", qualified=BASE_QUALIFIED)
    assert {ref["file"] for ref in picked["overridden_by"]} == {"pkg/locks.py", "pkg/threads.py"}
    assert picked["file"] == "pkg/harvest.py"
    assert {c["qualified"] for c in picked["candidates"]} == {
        BASE_QUALIFIED,
        A_QUALIFIED,
        B_QUALIFIED,
    }

    missed = tools.dossier("harvest", qualified="pkg.nowhere.NotAClass.harvest")
    assert missed["found"] is False
    assert "overridden_by" not in missed


## @brief Two same-named identities in ONE file are still told apart.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_two_identities_in_one_file_are_still_distinguishable(tmp_path: Path) -> None:
    """WHY THE SELECTOR IS NOT THE `file` SUBSTRING `Candidate` used to promise. Two classes in
    one module, each with a `harvest`, is ordinary Python — and a file substring cannot separate
    them, so it would have resolved gh#37's motivating example and failed the general case.

    This is the control on the DESIGN CHOICE, not on the plumbing, which is why it exists
    separately from the tests above: they would all pass against a file-substring
    implementation."""
    db = tmp_path / "onefile.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'pkg/both.py')")
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', 'harvest', 1, 1, ?, ?, ?, '(self)', '', '', 0)",
        [
            (1, 10, 20, "Any pkg.both.First.harvest"),
            (2, 30, 40, "Any pkg.both.Second.harvest"),
        ],
    )
    conn.commit()
    conn.close()

    first = q.resolve_symbol(db, "harvest", "pkg.both.First.harvest")
    second = q.resolve_symbol(db, "harvest", "pkg.both.Second.harvest")
    assert first is not None and second is not None
    assert (first.rowid, first.line_start) == (1, 10)
    assert (second.rowid, second.line_start) == (2, 30)
    assert first.file == second.file == "pkg/both.py", "same file — only the identity differs"


## @brief `chain_trace` refuses the selector rather than half-honouring it.
## @return None.
## @version 1
def test_chain_trace_does_not_accept_the_selector() -> None:
    """AN HONEST BOUNDARY, PINNED. `chain_trace` returns `candidates` but its walk resolves
    every hop by bare name (`_call_hops`/`_key_hops` filter `memberdef.name=?`), so accepting
    a selector would give an identity-correct root over a name-scoped traversal — a second
    instance of exactly the unkept promise gh#37 is about.

    Pinned as a test because a later reader WILL notice the asymmetry and "fix" it for
    consistency. This says the omission is a decision. Delete it only together with making the
    traversal identity-scoped."""
    import inspect

    assert "qualified" not in inspect.signature(q.chain_trace).parameters, (
        "chain_trace must not accept `qualified` until its traversal resolves hops by "
        "identity rather than by bare name -- see its docstring"
    )
