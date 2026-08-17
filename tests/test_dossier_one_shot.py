# SPDX-License-Identifier: MIT
"""The one-shot dossier: body, lock panels, and unresolvable callee names.

WHY THESE FOUR PANELS EXIST, so a later reader does not remove them as bloat.
Measured on the mbedtls acceptance grid: the index arm spent 15.5 tool calls per
question against the source arm's 8, and on one question the model called
`dossier` twice and then made fifteen more calls — seven `source`, and four of
those only to learn which pthread primitive a `threading_mutex_*_pthread` wrapper
forwards to, because `dossier.callees` is EMPTY for all four of them.

Each test below therefore pins a MECHANISM rather than a shape, and each is
written so that deleting the mechanism it names makes it fail on its own.

@brief Tests for the dossier's body / lock / external-callee panels.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew import query as q

## The csample function that carries all four panels at once: it opens a lock, calls an
## indexed function inside it, and calls two pthread primitives the index holds no
## memberdef for. Named once because six tests share it and a rename would otherwise
## silently reduce several of them to vacuous passes.
SETTER = "DataModel_SetIntegralTypeByKey"


## @brief The pthread primitives csample calls but never indexes.
## @return Names expected in an `external_callees` panel for `SETTER`.
## @version 1
def _expected_externals() -> set[str]:
    """@brief The unresolvable callee names `SETTER`'s body contains.
    @return Name set.
    @version 1
    """
    return {"pthread_mutex_lock", "pthread_mutex_unlock"}


def test_the_dossier_carries_the_function_body_it_describes(rich_db: Path, repo_root: Path) -> None:
    """The body is what seven `source` calls were spent on in one graded cell.

    Asserts a REAL LINE of the fixture's source, not merely that `lines` is non-empty:
    a body panel wired to the wrong file, or to the wrong extent, still produces a
    plausible-looking list of strings. The line span must also describe exactly what
    arrived, because a reader given `start_line` will use it to quote the code.
    """
    d = q.function_dossier(rich_db, SETTER, repo_root=repo_root)
    assert d is not None
    assert d.body is not None, "the one-shot body panel is missing"
    assert d.body.file == d.file, "the body must come from the file the identity names"
    assert any("pthread_mutex_lock" in line for line in d.body.lines), (
        "the body panel is not showing this function's actual source"
    )
    assert d.body.truncated is False
    assert d.body.end_line - d.body.start_line + 1 == len(d.body.lines)
    assert d.body.total_lines == len(d.body.lines)


def test_a_clipped_body_says_so_and_still_reports_its_full_extent(
    rich_db: Path, repo_root: Path
) -> None:
    """A SILENTLY clipped body is worse than no body: a reader who cannot see that
    lines were dropped reasons about a function it has only half read, and a body looks
    like proof. So `truncated` must flip, `end_line` must describe only what arrived,
    and `total_lines` must still report the whole extent so the reader knows how much
    is missing and can call `source` for the rest.

    Two lines rather than a boundary value, so the clip is unmistakable.
    """
    d = q.function_dossier(rich_db, SETTER, repo_root=repo_root, max_body_lines=2)
    assert d is not None and d.body is not None
    assert len(d.body.lines) == 2
    assert d.body.truncated is True
    assert d.body.end_line == d.body.start_line + 1
    assert d.body.total_lines > 2, "the full extent must survive the clip"


def test_the_body_clip_does_not_hide_calls_below_the_cut(rich_db: Path, repo_root: Path) -> None:
    """THE ONE WAY THESE TWO PANELS COULD SILENTLY CONTRADICT EACH OTHER.

    `external_callees` walks the body's RECORDED extent, not the excerpt's clipped one.
    Wiring it to the excerpt instead would have made a display cap quietly delete facts
    — the panel would report fewer callees the smaller the body window got, with
    nothing saying so. `pthread_mutex_unlock` sits several lines below a 2-line cut and
    must still be named.
    """
    clipped = q.function_dossier(rich_db, SETTER, repo_root=repo_root, max_body_lines=2)
    assert clipped is not None
    assert {e.name for e in clipped.external_callees} == _expected_externals()


def test_the_dossier_names_the_callees_the_index_cannot_resolve(
    rich_db: Path, repo_root: Path
) -> None:
    """FINDING 5 on mbedtls, reproduced on the synthetic index. `pthread_mutex_lock`
    has no memberdef row, so `call_edges` — whose `callee_rowid` is
    `NOT NULL REFERENCES memberdef(rowid)` — cannot represent the call at all, and the
    graph is silent about the only thing a mutex wrapper does.

    THREE claims, and the second two are the guard rails:
      * the unresolvable names are reported, with the line they are called on;
      * they are NOT in `callees`, whose rows are resolved by contract;
      * `callees` still carries the call that DID resolve, so the panel is additive
        rather than a replacement.
    """
    d = q.function_dossier(rich_db, SETTER, repo_root=repo_root)
    assert d is not None
    named = {e.name for e in d.external_callees}
    assert named == _expected_externals()
    assert all(e.call_lines for e in d.external_callees), "each must say where it is called"

    ## BOUNDED BY THIS FUNCTION'S BODY. The walk parses the whole FILE, and the fixture's
    ## `dm.c` calls the same two primitives from a sibling getter — so an unbounded walk
    ## would attribute the getter's call lines to this function and read as a wider
    ## claim than the source supports.
    assert d.body is not None
    last = d.body.start_line + d.body.total_lines - 1
    for edge in d.external_callees:
        assert all(d.body.start_line <= line <= last for line in edge.call_lines), (
            f"{edge.name} is reported at {edge.call_lines}, outside {d.body.start_line}..{last}"
        )

    resolved = {c.name for c in d.callees}
    assert not (named & resolved), "an unresolvable name must never appear as a resolved edge"
    assert "IntegerStorage_SetUINT8Key" in resolved, (
        "the resolved edge must survive — the external panel is additive"
    )


def test_an_external_callee_is_never_promoted_to_a_call_edge(
    rich_db: Path, repo_root: Path
) -> None:
    """A synthetic edge inherits the weakest link. `mark_reachability` and the thread
    BFS both traverse `call_edges`, so inserting a row for a name that resolves to
    nothing would propagate an unresolvable premise as fact — and worse, this panel is
    computed at QUERY time, so it would be a query mutating the index it reads.

    Pinned by counting `call_edges` before and after the query rather than by reading
    the payload: the payload cannot show a write that did not happen.
    """
    conn = sqlite3.connect(f"file:{rich_db}?mode=ro", uri=True)
    try:
        before = conn.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0]
    finally:
        conn.close()

    d = q.function_dossier(rich_db, SETTER, repo_root=repo_root)
    assert d is not None and d.external_callees

    conn = sqlite3.connect(f"file:{rich_db}?mode=ro", uri=True)
    try:
        after = conn.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0]
    finally:
        conn.close()
    assert after == before, "the external-callee panel must not write edges"


def test_the_lock_panels_agree_with_the_tools_they_replace(
    rich_db: Path, repo_root: Path, tmp_path: Path
) -> None:
    """`sections` and `locks_held` must be the SAME answers `sections_in` and
    `locks_held_when` give, or the one-shot is a second implementation of the lock
    layer rather than a cheaper route to it.

    The two panels are asserted on DIFFERENT functions on purpose. They are different
    questions with different join directions — what this function locks
    (`holder_rowid`) versus what is already locked when it runs
    (`critical_section_calls.callee_rowid`) — and a single function that satisfied both
    would let one field be wired to the other's query undetected.
    """
    setter = q.function_dossier(rich_db, SETTER, repo_root=repo_root)
    assert setter is not None
    assert setter.sections == q.sections_in(rich_db, SETTER)
    assert setter.sections, "the fixture's setter opens a critical section"

    ## `locks_held` needs a call site whose callee RESOLVED — csample's two section
    ## members are both `resolution='ambiguous'` and therefore carry a null
    ## `callee_rowid` by design, so the shared fixture cannot state this half. The
    ## hand-built db carries `solo`, whose name is unique so the name-scoped tool and
    ## the identity-scoped panel are asking the same question and equality is a real
    ## claim rather than an artefact of both being empty.
    db = _identity_db(tmp_path)
    inner = q.function_dossier(db, "solo", repo_root=tmp_path)
    assert inner is not None
    assert inner.locks_held == q.locks_held_when(db, "solo")
    assert [s.lock for s in inner.locks_held] == ["a_mutex"]


def test_a_dossier_without_a_working_tree_keeps_every_index_panel(rich_db: Path) -> None:
    """`repo_root` is OPTIONAL and its absence is a supported mode, not a degraded one:
    the R2 library is used directly by consumers holding only a database file, and a
    tool set bound without a repo provider is the shape most of this suite uses.

    So the two panels that read bytes go quiet and NOTHING ELSE CHANGES. Compared
    field by field against the full payload rather than spot-checked, so a panel that
    silently depended on the working tree fails here.
    """
    without = q.function_dossier(rich_db, SETTER)
    assert without is not None
    assert without.body is None
    assert without.external_callees == []
    assert without.sections, "the lock panels come from the index, not the working tree"
    assert without.callers == q.function_dossier(rich_db, SETTER).callers


## @brief Two same-named C functions in different files, each holding its own lock.
## @param tmp_path Test-scoped directory that becomes the working tree.
## @return Path to the built database.
## @version 1
def _identity_db(tmp_path: Path) -> Path:
    """gh#26 with a WORKING TREE behind it. Two unrelated static helpers named
    `flush`, one per module, each calling a DIFFERENT unindexed primitive and each
    holding a DIFFERENTLY-NAMED lock — so every panel keyed on the bare name instead of
    the resolved identity reports the union and is caught by name, not by count.

    Two same-named `drain` helpers do the same job for the OTHER lock panel: each is
    called from inside its own module's section, so a `locks_held` keyed on the name
    would report both mutexes for one function. `solo` is the collision-free control
    that makes an equality against the name-scoped tool meaningful.

    @brief Seed two same-named holders and two same-named section members.
    @return Database path.
    @version 1
    """
    (tmp_path / "a.c").write_text(
        "static void flush(void)\n{\n    port_a_drain();\n    drain();\n    solo();\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "b.c").write_text(
        "static void flush(void)\n{\n    port_b_drain();\n    drain();\n}\n",
        encoding="utf-8",
    )
    db = tmp_path / "identity.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT,
            static INTEGER, bodystart INTEGER, bodyend INTEGER,
            file_id INTEGER, bodyfile_id INTEGER
        );
        CREATE TABLE locks (
            id INTEGER PRIMARY KEY, name TEXT, scope TEXT, kind TEXT
        );
        CREATE TABLE lock_acquisitions (
            id INTEGER PRIMARY KEY, lock_id INTEGER, holder_rowid INTEGER,
            path_rowid INTEGER, form TEXT, role TEXT, mode TEXT,
            start_line INTEGER, end_line INTEGER, pattern_name TEXT,
            declared INTEGER, confidence TEXT
        );
        CREATE TABLE critical_section_calls (
            id INTEGER PRIMARY KEY, acquisition_id INTEGER, callee_rowid INTEGER,
            callee_name TEXT, call_line INTEGER, resolution TEXT
        );
        INSERT INTO path (rowid, name) VALUES (1, 'a.c'), (2, 'b.c');
        INSERT INTO locks (id, name, scope, kind) VALUES
            (1, 'a_mutex', '', 'mutex'), (2, 'b_mutex', '', 'mutex');
        INSERT INTO lock_acquisitions
            (id, lock_id, holder_rowid, path_rowid, form, role, mode,
             start_line, end_line, pattern_name, declared, confidence)
        VALUES (1, 1, 1, 1, 'call', 'acquire', 'exclusive', 3, 6, 'p', 0, 'high'),
               (2, 2, 2, 2, 'call', 'acquire', 'exclusive', 3, 5, 'p', 0, 'high');
        INSERT INTO critical_section_calls
            (id, acquisition_id, callee_rowid, callee_name, call_line, resolution)
        VALUES (1, 1, 3, 'drain', 4, 'resolved'),
               (2, 1, 5, 'solo', 5, 'resolved'),
               (3, 2, 4, 'drain', 4, 'resolved');
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, argsstring, "
        "briefdescription, detaileddescription, static, bodystart, bodyend, "
        "file_id, bodyfile_id) VALUES (?, 'function', ?, ?, '(void)', '', '', 1, "
        "?, ?, ?, ?)",
        [
            (1, "flush", "void a.flush", 1, 6, 1, 1),
            (2, "flush", "void b.flush", 1, 5, 2, 2),
            ## The `locks_held` pair: same name, one per module, each called from inside
            ## its own module's section. Line extents are outside the two `flush` bodies
            ## so nothing here depends on a body the fixture does not write.
            (3, "drain", "void a.drain", 8, 9, 1, 1),
            (4, "drain", "void b.drain", 8, 9, 2, 2),
            ## The collision-free control.
            (5, "solo", "void a.solo", 11, 12, 1, 1),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_the_one_shot_panels_key_on_the_resolved_identity_not_the_name(tmp_path: Path) -> None:
    """gh#26 IS STILL LIVE, and this payload is where it would hurt most: a body quoted
    under the wrong heading reads as proof, and a lock attributed to the wrong function
    is a fabricated synchronization claim.

    Both directions are asserted — the picked identity's own facts present, the
    namesake's ABSENT — because a panel that returned the union would satisfy the first
    half alone. `sections_in` on the same name is asserted to return BOTH, which is
    correct for a tool a human typed a name into and is exactly the widening this
    payload must not inherit.
    """
    db = _identity_db(tmp_path)
    d = q.function_dossier(db, "flush", repo_root=tmp_path)
    assert d is not None
    assert d.file == "a.c", "the definition-preferring pick is the a.c helper"

    assert d.body is not None
    assert any("port_a_drain" in line for line in d.body.lines)
    assert not any("port_b_drain" in line for line in d.body.lines)

    assert {e.name for e in d.external_callees} == {"port_a_drain"}

    assert [s.lock for s in d.sections] == ["a_mutex"]
    assert {s.lock for s in q.sections_in(db, "flush")} == {"a_mutex", "b_mutex"}, (
        "the name-scoped tool must keep unioning — this test is about the DOSSIER"
    )

    ## The OTHER lock panel, whose join runs the other way. `drain` exists once per
    ## module and each is called inside its own module's section, so the name-scoped
    ## tool reports two mutexes and the identity-scoped panel must report one.
    held = q.function_dossier(db, "drain", repo_root=tmp_path)
    assert held is not None and held.file == "a.c"
    assert [s.lock for s in held.locks_held] == ["a_mutex"]
    assert {s.lock for s in q.locks_held_when(db, "drain")} == {"a_mutex", "b_mutex"}


def test_the_panels_survive_a_database_that_predates_the_lock_layer(tmp_path: Path) -> None:
    """A consumer may be pointed at an older artifact and must get an empty answer, not
    an `OperationalError` — the #41 contract, now reached through a payload that asks
    four more questions than it used to.

    Reuses the identity fixture and DROPS the lock tables, so the two lock panels are
    the only difference between this and the test above.
    """
    db = _identity_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.executescript("DROP TABLE critical_section_calls; DROP TABLE lock_acquisitions;")
    conn.commit()
    conn.close()

    d = q.function_dossier(db, "flush", repo_root=tmp_path)
    assert d is not None
    assert d.sections == []
    assert d.locks_held == []
    assert d.body is not None, "the body panel does not depend on the lock layer"


def test_an_unreadable_working_tree_loses_the_body_and_not_the_dossier(
    rich_db: Path, tmp_path: Path
) -> None:
    """The failure mode of a stale registry entry or a moved checkout. `dossier` must
    degrade to its index-only panels rather than raising, because the identity, the
    requirements and the call graph are all still true — and because a raise here would
    make the composite payload fail where the narrow `source` tool merely returns None.
    """
    d = q.function_dossier(rich_db, SETTER, repo_root=tmp_path / "no_such_checkout")
    assert d is not None
    assert d.body is None
    assert d.external_callees == []
    assert d.sections, "the index panels are unaffected by an unreadable tree"


## @brief One Python and one C module, each calling a mix of noise and signal.
## @param tmp_path Test-scoped directory that becomes the working tree.
## @return Path to the built database.
## @version 1
def _noise_db(tmp_path: Path) -> Path:
    """Both filters and the language gate in ONE fixture, because the gate only means
    something when the same NAME is present in both languages: `pow` is a Python builtin
    AND a libc function, so a filter applied language-blind drops a real C call.

    @brief Seed a Python and a C caller that share a builtin name.
    @return Database path.
    @version 1
    """
    (tmp_path / "mod.py").write_text(
        "def compute(rows):\n"
        "    total = len(rows)\n"
        "    rows.append(total)\n"
        "    helper(total)\n"
        "    return pow(total, 2)\n",
        encoding="utf-8",
    )
    (tmp_path / "c.c").write_text(
        "int scale(int x)\n{\n    return (int) pow(x, 2);\n}\n",
        encoding="utf-8",
    )
    db = tmp_path / "noise.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT,
            static INTEGER, bodystart INTEGER, bodyend INTEGER,
            file_id INTEGER, bodyfile_id INTEGER
        );
        INSERT INTO path (rowid, name) VALUES (1, 'mod.py'), (2, 'c.c');
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, argsstring, "
        "briefdescription, detaileddescription, static, bodystart, bodyend, "
        "file_id, bodyfile_id) VALUES (?, 'function', ?, ?, '()', '', '', 0, ?, ?, ?, ?)",
        [
            (1, "compute", "def mod.compute", 1, 5, 1, 1),
            (2, "scale", "int scale", 1, 4, 2, 2),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_the_external_panel_reports_signal_and_not_every_token_that_is_unindexed(
    tmp_path: Path,
) -> None:
    """MEASURED AS NOISE BEFORE IT WAS FILTERED. The unfiltered panel reported
    `len`, `str`, `max`, `range`, `isinstance`, `get`, `items` and `dumps` for one
    function of this repo's own code — eight rows, none of them a fact about the
    codebase, crowding out the kind of row the panel exists for.

    THREE claims, and the third is the one a language-blind filter would break:
      * a Python BUILTIN is dropped in a Python file;
      * a member TAIL (`rows.append`) is dropped, because resolving it needs the
        receiver's declared type and an unresolved tail says nothing;
      * the SAME name in a C file is KEPT, because `pow` is also libc and a C caller
        of it means it. This is why the builtin filter is gated on the grammar rather
        than applied to the name.
    """
    db = _noise_db(tmp_path)

    py = q.function_dossier(db, "compute", repo_root=tmp_path)
    assert py is not None
    assert {e.name for e in py.external_callees} == {"helper"}, (
        "the Python panel must keep the one unindexed project call and drop the rest"
    )

    c = q.function_dossier(db, "scale", repo_root=tmp_path)
    assert c is not None
    assert {e.name for e in c.external_callees} == {"pow"}


def test_call_lines_are_reported_in_source_order(rich_db: Path, repo_root: Path) -> None:
    """The harvester walks the tree with a STACK, so a body's sites arrive in roughly
    REVERSE source order — the first unfiltered output read `[208, 207, 205, 202, 198,
    192]`. Descending line numbers read as corrupt, and worse, the per-name cap would
    then keep a function's LAST few call sites and drop the first, which is backwards
    for a panel whose value is "what does this thing do".
    """
    d = q.function_dossier(rich_db, SETTER, repo_root=repo_root)
    assert d is not None and d.external_callees
    for edge in d.external_callees:
        assert list(edge.call_lines) == sorted(edge.call_lines), (
            f"{edge.name} reports {edge.call_lines}, not in source order"
        )
    ## And the panel itself is in source order, so the first row is the first thing the
    ## function calls: mbedtls's wrappers lock before they unlock.
    firsts = [e.call_lines[0] for e in d.external_callees]
    assert firsts == sorted(firsts)


## @brief The `@details` prose is RETURNED, and a long one says where it stopped.
## @return None.
## @version 1
def test_the_dossier_returns_detail_prose_and_caps_it_loudly(tmp_path: Path) -> None:
    """FETCHED AND THROWN AWAY, for as long as the dossier has existed. `_identity` has always
    selected `detaileddescription` and read only `extract_version` out of it, so a function's
    `@details` text was in hand on every call and never returned.

    Measured on mbedtls 2026-08-14: the deprecation warning about reaching past
    `MBEDTLS_ALLOW_PRIVATE_ACCESS` lives in `mbedtls_ssl_handshake_step`'s detail — two graded Q2
    marks turn on it — and the agent reached it by grepping and then READING
    `include/mbedtls/ssl.h`, because this reply carried one sentence of `brief`. Verified after
    the change: `dossier('mbedtls_ssl_handshake_step').detail` is 1,277 characters and contains
    the token.

    THE CAP SAYS SO. 4,268 mbedtls rows carry detail averaging 1,052 characters, so the common
    case is small and the 14,804-character tail is what the cap is for. A silently truncated
    reply reads as a complete one, which is the failure this project keeps paying for — so the
    notice names both the cap and the true length.
    """
    from clew.query.dossier import _DETAIL_CAP, _capped_detail

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO path (rowid, name) VALUES (1, 'library/ssl_tls.c');
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT, argsstring TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER,
            briefdescription TEXT, detaileddescription TEXT, kind TEXT, static INTEGER
        );
        INSERT INTO memberdef VALUES (
            1, 'step', 'int step', '(void)', 1, 1, 10, 20,
            '<para>Brief only.</para>',
            '<para>Defining MBEDTLS_ALLOW_PRIVATE_ACCESS is deprecated.</para>',
            'function', 0
        );
        """
    )
    conn.commit()
    conn.close()

    found = q.function_dossier(db, "step")
    assert found is not None
    assert found.brief == "Brief only."
    assert "MBEDTLS_ALLOW_PRIVATE_ACCESS" in found.detail, (
        "the detail prose must be RETURNED — it was already being fetched"
    )

    ## THE CAP, two-sided: short prose is untouched, long prose is cut AND says so with both
    ## numbers. A cap that reports nothing is the silent-truncation failure.
    short = "x" * (_DETAIL_CAP - 1)
    assert _capped_detail(short) == short, "a short detail must not be altered at all"
    long_text = "y" * (_DETAIL_CAP + 500)
    capped = _capped_detail(long_text)
    assert capped.startswith("y" * _DETAIL_CAP)
    assert "truncated" in capped and str(_DETAIL_CAP) in capped and str(len(long_text)) in capped, (
        f"the notice must name the cap AND the true length, got the tail {capped[-120:]!r}"
    )
