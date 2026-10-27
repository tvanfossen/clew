# SPDX-License-Identifier: MIT
"""clew SERVED THE SPELLING, THEN REFUSED IT (C7).

**MEASURED BY REPLAYING ALL 48 FROZEN `index_only` TRANSCRIPTS** from the 1.1.0 grid. Of 157
`dossier` subjects that came back `found: false`, **147 — 93.6% — were strings clew itself had
put in front of the model in an earlier reply.** By shape:

| shape                   | n  |     %  | where it goes          |
|-------------------------|---:|-------:|------------------------|
| a FILE PATH             | 75 | 47.8%  | C1, landed             |
| a QUALIFIED C++ name    | 33 | 21.0%  | here                   |
| a bare name with no row | 49 | 31.2%  | genuinely absent       |

The 33 sit in entropic Q1, Q3 and Q4 — gaps of −17.5, −21.1 and −28.4, three of the six worst
clusters on the grid. Replay names the source exactly. `search(corpus="threads")` serves:

    {"name": "HealthMonitor::monitor_loop", "entry": "monitor_loop", ...}

and the tool's own prose tells the reader a row's name is what goes back to `dossier`. The model
did that, three cells out of three, and spent two of its six calls on the refusals before
retrying bare. The row was carrying the accepted spelling in `entry` the whole time and said
nothing about which of the two fields is a subject. The same shape appears under
`spawn_function` (7 subjects) and `candidates[i].qualified` (6).

THE ROW'S `name` CANNOT SIMPLY BE MADE BARE. `UNIQUE(name, entry, kind)` is what stops four
distinct threads collapsing into one row — the defect fixed in `clew/threads.py` one release ago
— so the qualified spelling is load-bearing there. The other side has to give.

**AND clew ALREADY HOLDS THIS TRANSFORMATION CORRECT.** `recovery._hint_from` tells the model, in
so many words, to pass `subject="<tail>", qualified="<whole>"`. That is a deterministic rewrite of
the caller's own string; charging a round trip to have the model perform it is the round trip this
test deletes.

PURELY ADDITIVE, AND THAT IS THE SAFETY ARGUMENT. The split fires only after ordinary resolution
has returned nothing, so no subject that resolves today can change meaning — including a file path
(C1) and a Python dotted name that is genuinely indexed under its full spelling.

@brief A qualified spelling is a usable subject.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q


##
# @brief An index holding two same-named methods under different owners.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def owned(tmp_path: Path) -> Path:
    """The entropic shape: `monitor_loop` is a method, the index holds it under the bare name,
    and every surface that names it — the thread row, the caller row, the candidate — spells it
    `HealthMonitor::monitor_loop`.

    A SECOND OWNER IS PLANTED DELIBERATELY. With one `monitor_loop` in the index the bare retry
    works and the qualified spelling is merely redundant; with two, the bare name is ambiguous and
    the qualified one is the only thing that selects an identity. That is the case where the round
    trip is not just wasted but cannot be completed in one more call.

    @brief Seed two same-named methods under different owners.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.execute("INSERT INTO path (rowid, name, type) VALUES (1, 'src/mcp/health.cpp', 1)")
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?, ?, '()', ?, '', 0)",
        [
            (1, "monitor_loop", 20, 60, "void HealthMonitor::monitor_loop", "the health loop"),
            (2, "monitor_loop", 80, 120, "void Watchdog::monitor_loop", "the watchdog loop"),
        ],
    )
    conn.commit()
    conn.close()
    return db


## @brief A qualified subject resolves to the identity it names.
## @version 1
def test_a_qualified_subject_resolves_to_that_identity(owned: Path) -> None:
    """RED BEFORE THE FIX: `resolve_subject` probes `memberdef.name`, which holds `monitor_loop`,
    so the qualified spelling matches nothing and the reply is a definitive negative about a
    symbol the index describes fully.

    Asserted on WHICH identity came back, not merely that something did. Returning the other
    owner's method would be worse than the refusal it replaces — a confident answer about the
    wrong function is the failure this repository keeps paying for.
    """
    built = q.dossier(owned, "HealthMonitor::monitor_loop")
    assert built is not None, "a qualified spelling clew serves must be a usable subject"
    assert built.kind == "function"
    assert built.function.brief == "the health loop", (
        f"resolved the wrong owner's method: {built.function.brief!r}"
    )


## @brief Both owners are separately reachable by their own qualified spelling.
## @version 1
def test_each_owner_is_reachable_by_its_own_spelling(owned: Path) -> None:
    """THE PROPERTY THAT MAKES IT A SELECTOR RATHER THAN A FALLBACK. If the split resolved to
    whichever row sorted first, one of these two would be unreachable and the reply would be
    labelled with the name of the function the caller asked for — which is the `_classify` failure
    this repo records: an arbitrary pick reported as the answer.
    """
    briefs = {
        name: q.dossier(owned, name).function.brief
        for name in ("HealthMonitor::monitor_loop", "Watchdog::monitor_loop")
    }
    assert briefs == {
        "HealthMonitor::monitor_loop": "the health loop",
        "Watchdog::monitor_loop": "the watchdog loop",
    }, briefs


## @brief The bare name keeps resolving exactly as it did.
## @version 1
def test_the_bare_name_is_unchanged(owned: Path) -> None:
    """THE SAFETY ASSERTION. The split must fire only after ordinary resolution has failed, so a
    bare name must still resolve, still be ambiguous between the two owners, and still disclose
    the ambiguity through `candidates` rather than being silently split.
    """
    built = q.dossier(owned, "monitor_loop")
    assert built is not None
    assert built.kind == "function"
    assert len(built.function.candidates) == 2, (
        "a bare name with two identities must still report both — the split is a last resort, "
        "never a replacement for disclosing ambiguity"
    )


## @brief A qualified spelling naming nothing is still a definitive negative.
## @version 1
def test_a_qualified_spelling_for_an_absent_owner_still_misses(owned: Path) -> None:
    """THE SPLIT MUST NOT INVENT A HIT. `Nonexistent::monitor_loop` has an indexed TAIL, which is
    precisely the shape that would resolve if the implementation split the string and then ignored
    the owner. Answering it would describe one of the two real methods under a name that is not
    theirs.

    This is the `absence is not emptiness` half of the fix: a spelling the index does not hold
    must still come back as a miss, and the recovery hint — which already tells the caller to
    split — remains the right reply for it.
    """
    assert q.dossier(owned, "Nonexistent::monitor_loop") is None


## @brief An explicit `qualified` argument still wins over a qualified subject.
## @version 1
def test_an_explicit_selector_is_not_overridden_by_the_split(owned: Path) -> None:
    """A caller that passed BOTH has disambiguated deliberately, and the documented rule is that
    `subject` stays bare when `qualified` is supplied. The split must not reinterpret the subject
    out from under an explicit selector — and a contradictory pair must refuse rather than pick,
    for the same reason an explicit `kind` is a filter and never an override.
    """
    built = q.dossier(owned, "monitor_loop", qualified="Watchdog::monitor_loop")
    assert built is not None
    assert built.function.brief == "the watchdog loop"

    ## Subject and selector naming different identities: the selector is what the caller
    ## disambiguated with, so it decides, and the contradiction cannot silently resolve to the
    ## subject's own owner.
    conflicting = q.dossier(
        owned, "HealthMonitor::monitor_loop", qualified="Watchdog::monitor_loop"
    )
    assert conflicting is None or conflicting.function.brief == "the watchdog loop", (
        "an explicit selector must not be overridden by a qualified subject"
    )


## @brief A file path is tried as a file before being split as a qualified name.
## @version 1
def test_a_file_path_is_not_mistaken_for_a_qualified_name(tmp_path: Path) -> None:
    """ORDER OF RESOLUTION, PINNED. `src/app.ts` contains a `.`, so a split-first implementation
    would read it as owner `src/app` and member `ts`. C1 made a path a subject in its own right,
    and the two features have to compose: the path resolves as a FILE, and the split never sees
    it.
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.execute("INSERT INTO path (name, type) VALUES ('src/app.ts', 1)")
    conn.commit()
    conn.close()

    built = q.dossier(db, "src/app.ts")
    assert built is not None
    assert built.kind == "file", f"a path must resolve as a file, not be split: {built.kind}"


# ─── the spelling the model actually produced: partial qualification ─────────


##
# @brief An index whose qualified names carry a namespace the caller omits.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def namespaced(tmp_path: Path) -> Path:
    """REPLAYED AGAINST THE LIVE entropic INDEX, which is how the first version of C7 was found
    to cover only a quarter of the measured misses. Two qualified spellings are in circulation
    and only one was accepted:

        qualified_name_of        -> entropic::HealthMonitor::monitor_loop   (what the index holds)
        threads[].name           -> HealthMonitor::monitor_loop            (what clew SERVES)

    Of the 12 distinct qualified subjects that missed on entropic's frozen cells, 3 carried the
    namespace and 9 did not. An exact-match split resolved exactly those 3. The spelling a reader
    writes — and the one the thread corpus hands them — omits the namespace.

    `Watchdog::monitor_loop` is planted under a DIFFERENT namespace so that the suffix
    `monitor_loop` alone is ambiguous while each `Owner::monitor_loop` is unique. That is the
    distinction the match has to make.

    @brief Seed namespaced qualified names.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.execute("INSERT INTO path (rowid, name, type) VALUES (1, 'src/mcp/health.cpp', 1)")
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?, ?, '()', ?, '', 0)",
        [
            (
                1,
                "monitor_loop",
                20,
                60,
                "void entropic::HealthMonitor::monitor_loop",
                "the health loop",
            ),
            (
                2,
                "monitor_loop",
                80,
                120,
                "void entropic::watchdog::Watchdog::monitor_loop",
                "the watchdog loop",
            ),
        ],
    )
    conn.commit()
    conn.close()
    return db


## @brief A partially qualified spelling resolves when it is unambiguous.
## @version 1
def test_a_partially_qualified_spelling_resolves(namespaced: Path) -> None:
    """THE SPELLING 9 OF 12 MEASURED MISSES ACTUALLY USED. `HealthMonitor::monitor_loop` is what
    `search(corpus="threads")` serves and what a reader writes; the index holds
    `entropic::HealthMonitor::monitor_loop`. An exact comparison refuses it, which is the refusal
    this whole finding is about.
    """
    built = q.dossier(namespaced, "HealthMonitor::monitor_loop")
    assert built is not None, "the spelling clew serves under threads[].name must be a subject"
    assert built.function.brief == "the health loop", built.function.brief

    other = q.dossier(namespaced, "Watchdog::monitor_loop")
    assert other is not None
    assert other.function.brief == "the watchdog loop", other.function.brief


## @brief An ambiguous suffix refuses rather than picking.
## @version 1
def test_an_ambiguous_suffix_does_not_resolve_to_an_arbitrary_owner(namespaced: Path) -> None:
    """THE BOUND ON THE MATCH, and the reason it is a suffix match and not a substring one. A
    suffix shared by two identities names neither, and answering it would be the arbitrary pick
    reported as the answer that this module's `also` field exists to prevent.

    `monitor_loop` bare is NOT this case — it resolves normally and discloses both through
    `candidates`. This is about a PARTIAL qualification that still fails to single one out.
    """
    from clew.query.subject import _split_qualified

    assert _split_qualified(namespaced, "::monitor_loop") is None, (
        "a suffix matching both identities must not resolve to whichever sorted first"
    )


## @brief The suffix must match at a separator boundary, not mid-identifier.
## @version 1
def test_the_suffix_must_align_to_a_separator(namespaced: Path) -> None:
    """`Monitor::monitor_loop` is a suffix of `entropic::HealthMonitor::monitor_loop` as a plain
    string — `HealthMonitor` ends with `Monitor` — and it names no owner in this index. Matching
    it would answer about `HealthMonitor` under a class name that does not exist, which is the
    confidently-wrong-symbol failure in its most literal form.
    """
    assert q.dossier(namespaced, "Monitor::monitor_loop") is None, (
        "a mid-identifier suffix is not a qualification and must not resolve"
    )
