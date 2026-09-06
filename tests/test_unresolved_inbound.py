# SPDX-License-Identifier: MIT
"""What an empty `callers` list is entitled to claim (gh#15).

`callers: []` is indistinguishable from "nothing calls this", which is a far
stronger statement than "no edge survived resolution" — and the reporter of gh#15
acted on the strong reading, followed the one caller offered (a test helper), and
shipped a design document recommending the wrong configuration call.

Every other empty answer on this surface is graded. `search` says what it did not
read; a stale index announces itself; an ambiguous name names its candidates;
`gates_unplaceable` reports the gates it could not place so an empty `gated_by`
cannot be read as "ungated". `callers: []` was the one place that overclaimed.

THE FIX IS A MEASUREMENT, NOT A SENTENCE, and that is not a style preference —
`mcp_server/emptiness.py` records the rule this project learned the hard way:

    fix the corpus, not the sentence about the corpus. A wording change that
    compensates for missing data hedges every honest answer to excuse one
    dishonest one.

and records gh#393, where a blanket "may be incomplete" note was built, measured,
and withdrawn for hedging nearly every reply. So a note attached to every class
member would be the same mistake a second time. Instead the BUILD records what it
refused: when a call site names a function and no edge survives resolution, the
candidate rowids are counted. `callers: []` beside `callers_unresolved: 3` is a
fact about this symbol; `callers: []` beside `callers_unresolved: 0` is a genuine
measured negative and keeps its full confidence.

@brief Tests for the recorded unresolved-inbound measurement.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew import query as q
from clew.call_edges import (
    SOURCE_AST,
    SOURCE_AST_MEMBER,
    _ast_record_call_edge,
    _insert_unresolved_inbound,
)


def test_a_refused_member_call_records_the_set_it_refused_between() -> None:
    """The refusal path emits no edge — correctly, since a name is not evidence of linkage —
    and used to leave no trace at all, so the fact that resolution was ATTEMPTED and failed was
    unrecoverable at query time. The whole candidate SET is kept, not each rowid separately,
    because whether the refusal is evidence about any one symbol depends on what else was in
    it."""
    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    unresolved: list[list[int]] = []
    _ast_record_call_edge(
        1,
        "store",
        {"store": [30, 31, 32]},
        resolved,
        fuzzy,
        SOURCE_AST_MEMBER,
        unresolved=unresolved,
    )
    assert resolved == [] and fuzzy == [], "premise: this call refuses"
    assert unresolved == [[30, 31, 32]]


def test_a_single_candidate_with_an_unverified_receiver_is_recorded_too() -> None:
    """The subtlest case and the one that burned gh#15's reporter. `obj.foo()` where exactly
    ONE indexed `foo` exists still earns no edge — the real receiver may be a class this index
    never saw — so `foo` reports `callers: []` while a call site plainly named it. That is
    precisely the empty list that must not read as a measured negative."""
    unresolved: list[list[int]] = []
    _ast_record_call_edge(1, "foo", {"foo": [42]}, [], [], SOURCE_AST_MEMBER, unresolved=unresolved)
    assert unresolved == [[42]]


def test_a_resolved_call_records_nothing() -> None:
    """THE CONTROL. A call that resolves is not an unresolved one, and counting it would
    inflate the measurement until every symbol looked doubtful — which is the blanket hedge
    this design exists to avoid."""
    resolved: list[tuple[int, int, str]] = []
    unresolved: list[list[int]] = []
    _ast_record_call_edge(
        1, "free_fn", {"free_fn": [7]}, resolved, [], SOURCE_AST, unresolved=unresolved
    )
    assert resolved == [(1, 7, SOURCE_AST)]
    assert unresolved == [], "a resolved call is not evidence of an unresolved one"


def test_a_callee_outside_the_index_records_nothing() -> None:
    """THE OTHER CONTROL, and the one that keeps the measurement attributable. A call to
    `std::to_string` has no candidate row, so there is no indexed function whose `callers`
    could be understated — the callee is simply not in the corpus. Counting it would produce a
    number attached to nothing, and on entropic 299 of 662 qualified sites are that shape."""
    unresolved: list[list[int]] = []
    _ast_record_call_edge(1, "to_string", {}, [], [], SOURCE_AST_MEMBER, unresolved=unresolved)
    assert unresolved == []


## One function doxygen wrote twice (a decl/def pair), and two unrelated functions that merely
## share a name — the two shapes the attribution rule has to separate.
_ONE_FUNCTION = ("store", "void C::store", "(int)")
_IDENTITIES = {
    30: _ONE_FUNCTION,
    31: _ONE_FUNCTION,
    40: ("store", "void A::store", "(int)"),
    41: ("store", "void B::store", "(int)"),
}


def test_only_a_refusal_that_names_ONE_function_is_credited(tmp_path: Path) -> None:
    """THIS RULE WAS FORCED BY A MEASUREMENT, and the first version of it was wrong.

    Crediting every candidate of every refused site recorded 1,716,524 site-candidate pairs on
    entropic and would have qualified 2,290 of the 2,620 functions with no inbound edge — 87%,
    which is a permanent banner rather than a signal. `emptiness.py` records exactly that
    outcome as gh#393's reason for withdrawal: an annotation on almost every reply trains a
    reader to ignore it.

    It was also wrong on its own terms. A site whose callee name matches 200 rows cannot be
    attributed to any of them, and crediting each is the name-as-evidence fallacy
    `_ast_record_call_edge` refuses one function up: a NAME is not evidence of linkage, so it
    is not evidence of a MISSING linkage either.

    So a refusal counts only where the candidate set is one function's decl/def pair. There the
    call site really did name that function and resolution declined for want of a verified
    receiver — gh#15's reported case exactly.
    """
    db = tmp_path / "u.db"
    conn = sqlite3.connect(str(db))
    written = _insert_unresolved_inbound(
        conn,
        [
            [30, 31],  # one function, written twice — attributable
            [30, 31],  # the same function refused again
            [40, 41],  # two DIFFERENT functions sharing a name — not attributable
        ],
        _IDENTITIES,
    )
    conn.commit()
    rows = dict(conn.execute("SELECT callee_rowid, sites FROM unresolved_inbound"))
    conn.close()
    assert written == 1
    # Credited to ONE rowid of the pair: the query layer sums over the identity's whole
    # decl/def pair, so crediting both would double every count.
    assert rows == {30: 2}, f"got {rows}"


def test_a_partly_unknown_candidate_set_is_not_attributable(tmp_path: Path) -> None:
    """FAIL CLOSED. A set whose rowids are only partly known cannot be SHOWN to name one
    function, and treating the unknown half as agreeing with the known half would credit a
    refusal that may span several. Unknown disqualifies the set."""
    db = tmp_path / "u.db"
    conn = sqlite3.connect(str(db))
    written = _insert_unresolved_inbound(conn, [[30, 999]], _IDENTITIES)
    conn.commit()
    rows = dict(conn.execute("SELECT callee_rowid, sites FROM unresolved_inbound"))
    conn.close()
    assert written == 0 and rows == {}


def test_an_index_with_no_identities_writes_no_table_at_all(tmp_path: Path) -> None:
    """THE DEGRADE THAT MUST NOT MANUFACTURE CONFIDENCE. Without `memberdef.definition` and
    `argsstring` nothing can be shown to name one function, so every symbol would record a zero
    — and a zero MEANS "measured, nothing was refused". That is a clean bill of health issued by
    a detector that could not look, which is this repository's standing failure mode. The table
    is left absent instead, so the query layer answers "cannot say"."""
    db = tmp_path / "u.db"
    conn = sqlite3.connect(str(db))
    _insert_unresolved_inbound(conn, [[30, 31]], {})
    conn.commit()
    present = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='unresolved_inbound'"
    ).fetchone()[0]
    conn.close()
    assert present == 0, "no measurement is possible, so no measurement is published"


def test_the_table_is_rebuilt_rather_than_appended(tmp_path: Path) -> None:
    """A refresh folds the WHOLE cached payload set, not only the changed files, so the
    measurement is recomputed in full every build. Appending would let a symbol's count grow
    with the number of times the index has been refreshed — a number about this repository's
    build history wearing the costume of a number about the code."""
    db = tmp_path / "u.db"
    conn = sqlite3.connect(str(db))
    _insert_unresolved_inbound(conn, [[30, 31], [30, 31]], _IDENTITIES)
    _insert_unresolved_inbound(conn, [[30, 31]], _IDENTITIES)
    conn.commit()
    rows = dict(conn.execute("SELECT callee_rowid, sites FROM unresolved_inbound"))
    conn.close()
    assert rows == {30: 1}, f"the second build's measurement replaces the first: {rows}"


## A minimal but real index: two functions, one of which has a recorded refusal.
_SCHEMA = """
CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);
CREATE TABLE memberdef (
    rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, type TEXT, argsstring TEXT,
    definition TEXT, scope TEXT, file_id INTEGER, bodyfile_id INTEGER,
    bodystart INTEGER, bodyend INTEGER, briefdescription TEXT, detaileddescription TEXT,
    static INTEGER
);
CREATE TABLE call_edges (
    caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT
);
INSERT INTO path (rowid, type, name) VALUES (1, 1, 'src/a.cpp');
INSERT INTO memberdef (rowid, name, kind, type, argsstring, definition, scope, file_id,
                       bodyfile_id, bodystart, bodyend, briefdescription,
                       detaileddescription, static) VALUES
    (10, 'reached_only_by_pointer', 'function', 'void', '()', 'void C::reached_only_by_pointer',
     'C', 1, 1, 4, 6, '', '', 0),
    (11, 'genuinely_uncalled', 'function', 'void', '()', 'void C::genuinely_uncalled',
     'C', 1, 1, 9, 11, '', '', 0);
"""


def _index(tmp_path: Path, *, with_measurement: bool) -> Path:
    db = tmp_path / "i.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA)
    if with_measurement:
        # Three call sites named `reached_only_by_pointer` and none resolved — each set names
        # that one function, so each is attributable. Nothing was ever refused against
        # `genuinely_uncalled`, so its empty caller list is a genuine measured negative.
        identities = {10: ("reached_only_by_pointer", "void C::reached_only_by_pointer", "()")}
        _insert_unresolved_inbound(conn, [[10], [10], [10]], identities)
    conn.commit()
    conn.close()
    return db


def test_an_empty_callers_list_reports_what_was_refused(tmp_path: Path) -> None:
    """gh#15's durable half. Both functions report `callers: []` and the two empty lists mean
    completely different things — one is a symbol whose callers all failed to resolve, the
    other is a symbol nothing calls. The reply now separates them."""
    db = _index(tmp_path, with_measurement=True)

    understated = q.dossier(db, "reached_only_by_pointer", max_body_lines=0)
    assert understated is not None and understated.function is not None
    assert understated.function.callers == [], "premise: no edge survived"
    assert understated.function.callers_unresolved == 3

    measured = q.dossier(db, "genuinely_uncalled", max_body_lines=0)
    assert measured is not None and measured.function is not None
    assert measured.function.callers == []
    assert measured.function.callers_unresolved == 0, (
        "a genuine measured negative keeps its full confidence — a zero here is the whole "
        "reason the count is recorded even when nothing refused"
    )


def test_an_index_without_the_measurement_says_it_cannot_tell(tmp_path: Path) -> None:
    """An index built before this was recorded has no table, and the absence of a count is NOT
    evidence that nothing was refused. Reporting 0 there would be exactly the substitution the
    field exists to prevent — "this index cannot tell" answered as "this is measured empty".
    """
    db = _index(tmp_path, with_measurement=False)
    doss = q.dossier(db, "reached_only_by_pointer", max_body_lines=0)
    assert doss is not None and doss.function is not None
    assert doss.function.callers_unresolved is None, (
        "no table means no measurement, which is not the same as a measured zero"
    )


def test_a_measured_refusal_is_named_in_the_note() -> None:
    """gh#15's reporter said option (3) alone — telling them the list was incomplete — would
    have prevented the error, and gh#4's reporter said the same about the constructor case.
    This is that note, now carrying a NUMBER instead of a category, so it fires on evidence
    about THIS symbol rather than on the kind of symbol it is."""
    from clew.mcp_server.tools_query import _empty_callers_note

    note = _empty_callers_note(
        {"subject_kind": "function", "callers": [], "callers_unresolved": 3}, ()
    )
    assert note, "an empty list with a recorded refusal must be qualified"
    assert "3" in note, f"the count is the evidence and must be shown: {note!r}"
    assert "receiver" in note, "the note must say what kind of call goes unresolved"


def test_a_measured_zero_gets_no_note() -> None:
    """THE LOAD-BEARING NEGATIVE, and the reason the build records a zero at all. A symbol
    nothing refused against has a genuinely empty caller list, and annotating it would be the
    blanket hedge `emptiness.py` withdrew in gh#393 — one that trains a reader to ignore the
    annotation, which is worse than no annotation."""
    from clew.mcp_server.tools_query import _empty_callers_note

    assert (
        _empty_callers_note(
            {"subject_kind": "function", "callers": [], "callers_unresolved": 0}, ()
        )
        == ""
    ), "a measured negative keeps its full confidence and says nothing extra"


def test_an_unmeasured_index_falls_back_to_the_constructor_rule() -> None:
    """An index with no measurement reports None, and None is not a count. The note must not
    read it as one — in either direction: it neither claims a refusal nor claims a clean
    negative. The older `also`-based constructor rule still applies on such an index, which is
    what keeps gh#4's fix working on a database built before gh#15."""
    from clew.mcp_server.tools_query import _empty_callers_note

    payload = {"subject_kind": "function", "callers": [], "callers_unresolved": None}
    assert _empty_callers_note(payload, ()) == "", "no measurement is not a refusal"
    assert "constructor" in _empty_callers_note(payload, ("class",)), (
        "gh#4's rule must survive on an index that predates gh#15's measurement"
    )


def test_the_measured_note_wins_over_the_constructor_heuristic() -> None:
    """When both apply, the measurement is the better answer: it counts what actually happened
    to THIS symbol, where `also` only says the name is shared with a class. Emitting both would
    make the reply argue with itself about which is the reason."""
    from clew.mcp_server.tools_query import _empty_callers_note

    note = _empty_callers_note(
        {"subject_kind": "function", "callers": [], "callers_unresolved": 2}, ("class",)
    )
    assert "2" in note and "constructor" not in note, f"got {note!r}"
