# SPDX-License-Identifier: MIT
"""Author-declared @emits/@handles event edges (task #47).

The catalog these tests cover was sitting fully formed in every a C++ codebase database
and read by nothing: doxygen rewrites an `@emits`-aliased xrefitem into
`<xrefsect id="evt_emits_...">` markup exactly as it does for `@req`, so the
producer/consumer graph the author wrote down was already stored and simply
never mined.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.cli import build_index
from clew.event_edges import (
    CONSUMER,
    PRODUCER,
    _declared_event_keys,
    _edges_for,
    _topic_roles,
    import_event_edges,
)

## The end-to-end tests below drive the REAL pipeline, because the defect they
## exist for lives at the `cli.py` call site rather than inside the importer: a
## parameter that every unit test can reach and no production caller ever passes.
## Same environment gate `tests/test_robustness.py` uses.
_NEEDS_DOXYGEN = pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="the end-to-end event-edge wiring tests need the real doxygen binary",
)

# The real shape doxygen emits, taken verbatim from a C++ reference build.
_EMITS = (
    '<para><xrefsect id="evt_emits_1_evt_emits000029"><xreftitle>Emits ingot event'
    "</xreftitle><xrefdescription><para>{topic} </para>\n</xrefdescription></xrefsect></para>"
)
_HANDLES = (
    '<para><xrefsect id="evt_handles_1_evt_handles000004"><xreftitle>Handles ingot event'
    "</xreftitle><xrefdescription><para>{topic} </para>\n</xrefdescription></xrefsect></para>"
)

_XREFITEM_ALIASES = (
    'ALIASES                = "req=@xrefitem req_trace \\"Requirement\\" \\"Traceability\\"" \\\n'
    '                         "handles=@xrefitem evt_handles \\"Handles ingot event\\" \\"H\\"" \\\n'
    '                         "emits=@xrefitem evt_emits \\"Emits ingot event\\" \\"E\\""\n'
)


## @brief Build a throwaway db carrying the memberdef columns the importer reads.
## @param path Database path to create.
## @param rows (rowid, name, is_definition, detaileddescription) tuples.
## @return None.
## @version 1
def _make_db(path: Path, rows: list[tuple[int, str, int, str]]) -> None:
    """@brief Create a minimal memberdef + shared_key_edges schema and seed it."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,
            file_id INTEGER, bodyfile_id INTEGER, detaileddescription TEXT
        );
        CREATE TABLE threads (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE shared_key_edges (
            writer_rowid INTEGER NOT NULL, reader_rowid INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            edge_kind TEXT NOT NULL CHECK(edge_kind IN ('state','event','unknown')),
            declared INTEGER NOT NULL CHECK(declared IN (0,1)),
            source TEXT NOT NULL CHECK(source IN
                ('shared_key_inferred','shared_key_declared')),
            confidence TEXT NOT NULL CHECK(confidence IN ('low','medium','high')),
            dispatch_mode TEXT NOT NULL DEFAULT 'unknown'
                CHECK(dispatch_mode IN ('inline','queued','keyed','unknown')),
            edge_triggered INTEGER CHECK(edge_triggered IN (0,1)),
            crosses_thread INTEGER CHECK(crosses_thread IN (0,1)),
            to_thread_id INTEGER REFERENCES threads(id),
            UNIQUE(writer_rowid, reader_rowid, key_name, source)
        );
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, detaileddescription) "
        "VALUES (?, 'function', ?, 1, ?, ?)",
        [(rid, name, 1 if is_def else 2, desc) for rid, name, is_def, desc in rows],
    )
    conn.commit()
    conn.close()


def test_declared_event_keys_reads_the_repos_own_aliases(tmp_path: Path) -> None:
    """The xrefitem KEY is repo-chosen, so it is read from the target's ALIASES
    rather than assumed. Only the author-facing TAG NAME is interpreted."""
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(_XREFITEM_ALIASES, encoding="utf-8")
    keys = _declared_event_keys(doxyfile, None)
    assert keys == {"evt_emits": PRODUCER, "evt_handles": CONSUMER}
    # req_trace is an alias too, but `req` is not an event verb — correctly ignored.
    assert "req_trace" not in keys


def test_unknown_tag_vocabulary_and_missing_doxyfile_are_correct_negatives(
    tmp_path: Path,
) -> None:
    """A repo with no event alias, and an unreadable/synthesized Doxyfile, both
    yield zero keys — empty, never an error."""
    plain = tmp_path / "Doxyfile"
    plain.write_text('ALIASES = "note=@xrefitem notes \\"Note\\" \\"Notes\\""\n', encoding="utf-8")
    assert _declared_event_keys(plain, None) == {}
    assert _declared_event_keys(tmp_path / "absent", None) == {}


def test_event_tag_vocabulary_is_overridable(tmp_path: Path) -> None:
    """A repo using its own verbs supplies a mapping instead of the defaults —
    the built-in vocabulary is a default, not a hardcoded assumption."""
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        'ALIASES = "broadcasts=@xrefitem bcast \\"B\\" \\"B\\"" \\\n'
        '          "reacts=@xrefitem rct \\"R\\" \\"R\\""\n',
        encoding="utf-8",
    )
    assert _declared_event_keys(doxyfile, None) == {}  # not in the default vocabulary
    keys = _declared_event_keys(doxyfile, {"broadcasts": PRODUCER, "reacts": CONSUMER})
    assert keys == {"bcast": PRODUCER, "rct": CONSUMER}


def test_edges_only_attach_to_rowids_that_carried_the_tag(tmp_path: Path) -> None:
    """REGRESSION for the bug this importer was first written with.

    `memberdef.name` is UNQUALIFIED: on a C++ codebase the name `react` maps to 60
    memberdefs, one per FSM class, of which exactly ONE declares `@handles`.
    The first implementation harvested tag-carrying NAMES and then re-resolved
    each name through a name index, fabricating an edge for the other 59 — 5294
    edges where 549 are real. An edge must only ever be attributed to a
    memberdef that actually carried the tag."""
    db = tmp_path / "evt.db"
    _make_db(
        db,
        [
            (1, "emit_it", 1, _EMITS.format(topic="EVENT:FOO")),
            (2, "react", 1, _HANDLES.format(topic="EVENT:FOO")),  # the ONE tagged react
            (3, "react", 1, "<para>a different class's react, no tag</para>"),
            (4, "react", 1, ""),  # and another
        ],
    )
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(_XREFITEM_ALIASES, encoding="utf-8")
    import_event_edges(db, doxyfile)

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, declared, "
        "dispatch_mode, edge_triggered FROM shared_key_edges"
    ).fetchall()
    conn.close()
    assert rows == [(1, 2, "EVENT:FOO", "event", 1, "keyed", 1)], (
        "untagged same-named functions must not inherit the edge"
    )


def test_decl_def_duplicate_collapses_to_the_definition(tmp_path: Path) -> None:
    """Doxygen documents one function twice when it is declared in a header and
    defined in a .cpp; both rows carry the tag. Collapse to the definition so a
    single logical emitter does not double its edges."""
    tagged = [
        ("EVENT:FOO", PRODUCER, "emit_it", 10, False),  # header declaration
        ("EVENT:FOO", PRODUCER, "emit_it", 11, True),  # definition
        ("EVENT:FOO", CONSUMER, "on_foo", 20, True),
    ]
    topics = _topic_roles(tagged)
    assert topics["EVENT:FOO"][PRODUCER] == {11}
    assert _edges_for(topics) == [(11, 20, "EVENT:FOO")]


def test_one_sided_topics_yield_no_edges(tmp_path: Path) -> None:
    """A topic emitted but never handled (or vice versa) produces no edge — it
    is reported as a diagnostic instead, since it usually means a real defect."""
    topics = _topic_roles(
        [
            ("EVENT:ORPHAN", PRODUCER, "emit_it", 1, True),
            ("EVENT:UNEMITTED", CONSUMER, "on_it", 2, True),
        ]
    )
    assert _edges_for(topics) == []


def test_repo_without_event_aliases_writes_nothing(tmp_path: Path) -> None:
    """demobot and every non-event repo: a correct negative, not an error."""
    db = tmp_path / "evt.db"
    _make_db(db, [(1, "f", 1, _EMITS.format(topic="EVENT:FOO"))])
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = synth\nINPUT =\n", encoding="utf-8")
    import_event_edges(db, doxyfile)

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM shared_key_edges").fetchone()[0] == 0
    conn.close()


# ─── the DECLARATION route, driven through the real pipeline ─────────────────


## @brief Write a tiny C++ repo whose event tags are named by the caller.
## @param root Repo root to create.
## @param emit_tag Author-facing tag name for the producing side.
## @param handle_tag Author-facing tag name for the consuming side.
## @return The Doxyfile path the pipeline should be driven with.
## @version 1
def _write_event_repo(root: Path, emit_tag: str, handle_tag: str) -> Path:
    """The two tags are parameters because the whole point of these tests is the
    difference between a vocabulary clew ships and one a repo declares —
    the SOURCE and the ALIASES are otherwise byte-identical between the two.

    @brief Create a two-function event repo and its Doxyfile.
    @return Path to the Doxyfile.
    @version 1
    """
    src = root / "src"
    src.mkdir(parents=True)
    (src / "bus.cpp").write_text(
        f"/// @brief Emit the foo event.\n"
        f"/// @{emit_tag} EVENT:FOO\n"
        f"void emit_foo() {{}}\n"
        f"\n"
        f"/// @brief React to the foo event.\n"
        f"/// @{handle_tag} EVENT:FOO\n"
        f"void on_foo() {{}}\n",
        encoding="utf-8",
    )
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"PROJECT_NAME = evtprobe\n"
        f"INPUT = {src}\n"
        f"OUTPUT_DIRECTORY = {root}/out\n"
        f"RECURSIVE = YES\n"
        f"EXTRACT_ALL = YES\n"
        f"GENERATE_SQLITE3 = YES\n"
        f'ALIASES = "{emit_tag}=@xrefitem evt_produce \\"Emits\\" \\"Emitted events\\"" \\\n'
        f'          "{handle_tag}=@xrefitem evt_consume \\"Handles\\" \\"Handled events\\""\n',
        encoding="utf-8",
    )
    return doxyfile


## @brief Build a repo through the real pipeline and return its event edges.
## @param root Repo root to index.
## @param doxyfile Doxyfile driving doxygen.
## @param out Output database path.
## @return (writer name, reader name, key_name) for every edge_kind='event' row.
## @version 1
def _built_event_edges(root: Path, doxyfile: Path, out: Path) -> list[tuple[str, str, str]]:
    """Names rather than rowids, because a rowid is an artefact of doxygen's own
    ordering and would make the assertion brittle for no gain.

    DRIVEN THROUGH `build_index`, the TYPED entry point, since the 22->6 collapse removed
    `--doxyfile` from the command line. An explicit Doxyfile is build mechanics rather than a
    declaration, so it kept its route on this surface — which is also the surface the MCP
    server uses, making this the more representative of the two doors.

    @brief Run the pipeline and read back the event edges by function name.
    @return Event edges as (writer, reader, topic) name triples.
    @version 2
    """
    build_index(output=out, repo_root=root, doxyfile=doxyfile)
    conn = sqlite3.connect(str(out))
    try:
        return conn.execute(
            "SELECT w.name, r.name, e.key_name FROM shared_key_edges e "
            "JOIN memberdef w ON w.rowid = e.writer_rowid "
            "JOIN memberdef r ON r.rowid = e.reader_rowid "
            "WHERE e.edge_kind = 'event' ORDER BY 1, 2, 3"
        ).fetchall()
    finally:
        conn.close()


@_NEEDS_DOXYGEN
def test_default_vocabulary_still_produces_event_edges_end_to_end(tmp_path: Path) -> None:
    """THE SUCCESS-PATH HALF. A target that declares NOTHING must keep getting
    DEFAULT_EVENT_TAGS and the same edges it got before the declaration section
    existed.

    Written because a check with a test for its failure path and none for its
    success path is this project's standing way of shipping something completely
    broken while the suite stays green — and because the declared-vocabulary test
    below is worthless without a control proving the pipeline reaches this
    importer at all."""
    root = tmp_path / "defaults"
    doxyfile = _write_event_repo(root, "emits", "handles")
    assert not (root / ".clew.yaml").exists(), "the control declares nothing"

    edges = _built_event_edges(root, doxyfile, tmp_path / "defaults.db")
    assert edges == [("emit_foo", "on_foo", "EVENT:FOO")]


@_NEEDS_DOXYGEN
def test_a_declared_event_vocabulary_reaches_the_importer(tmp_path: Path) -> None:
    """THE DEFECT ITSELF (task #317). `import_event_edges` has taken an
    `event_tags` override since it was written and `cli.py` never passed one, so
    the 17 built-in English verbs were the entire vocabulary with no route to
    change them: a repo whose bus is documented `@broadcasts`/`@reacts` got
    silence, and no unit test could see it because every unit test calls the
    importer directly and can hand it whatever it likes.

    So this drives the REAL pipeline. Deleting the argument at the call site
    turns it red again, which is the only check that the parameter is wired
    rather than merely present."""
    root = tmp_path / "declared"
    doxyfile = _write_event_repo(root, "broadcasts", "reacts")
    (root / ".clew.yaml").write_text(
        "event_tags:\n  broadcasts: producer\n  reacts: consumer\n", encoding="utf-8"
    )

    edges = _built_event_edges(root, doxyfile, tmp_path / "declared.db")
    assert edges == [("emit_foo", "on_foo", "EVENT:FOO")]


def test_a_declared_vocabulary_replaces_the_defaults_rather_than_merging(
    tmp_path: Path,
) -> None:
    """REPLACE, not merge — and this is the test that would catch merge semantics,
    because every other one here declares verbs the defaults do not have and
    passes either way.

    It is load-bearing rather than a style choice. `raises` is a built-in PRODUCER
    verb and an EXCEPTION verb in most codebases, so a repo aliasing
    `raises=@xrefitem exceptions ...` has its exception documentation mined as
    event production. Replacing is that repo's only fix; merging would leave it
    with no way to say "not that word"."""
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        'ALIASES = "broadcasts=@xrefitem bcast \\"B\\" \\"B\\"" \\\n'
        '          "emits=@xrefitem evt_emits \\"E\\" \\"E\\"" \\\n'
        '          "raises=@xrefitem exceptions \\"Throws\\" \\"Exceptions\\""\n',
        encoding="utf-8",
    )
    keys = _declared_event_keys(doxyfile, {"broadcasts": PRODUCER})

    assert keys == {"bcast": PRODUCER}
    assert "evt_emits" not in keys, "a declared vocabulary must REPLACE the defaults"
    assert "exceptions" not in keys, "an exception alias must stop being read as an emit"


def test_an_unrecognised_alias_is_named_in_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """THE DIAGNOSTIC. Before it, a repo using `@broadcasts` got zero rows and
    total silence — indistinguishable from a repo with no event bus at all, which
    is the same shape as the #29 undeclared-accessor case: the layer was empty
    because the detector had no way to look, not because there was nothing there.
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        'ALIASES = "broadcasts=@xrefitem bcast \\"B\\" \\"B\\"" \\\n'
        '          "reacts=@xrefitem rct \\"R\\" \\"R\\""\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.INFO, logger="clew.event_edges"):
        assert _declared_event_keys(doxyfile, None) == {}

    assert "broadcasts" in caplog.text and "reacts" in caplog.text
    assert "event_tags" in caplog.text, "the hint must name the declaration that claims them"


def test_a_fully_recognised_alias_set_logs_no_hint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """THE CONTROL. A diagnostic that fires on a repo whose vocabulary is already
    understood is noise, and noise is how a real hint stops being read — so the
    quiet case has to be pinned as hard as the loud one."""
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        'ALIASES = "emits=@xrefitem evt_emits \\"E\\" \\"E\\"" \\\n'
        '          "handles=@xrefitem evt_handles \\"H\\" \\"H\\""\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.INFO, logger="clew.event_edges"):
        keys = _declared_event_keys(doxyfile, None)

    assert keys == {"evt_emits": PRODUCER, "evt_handles": CONSUMER}
    assert "not recognised event verbs" not in caplog.text


@_NEEDS_DOXYGEN
def test_an_undeclared_repo_vocabulary_is_silent_without_the_declaration(
    tmp_path: Path,
) -> None:
    """The negative control for the test above, and the reason the diagnostic
    exists: the SAME repo with the SAME aliases and no declaration produces no
    event edges, because `broadcasts`/`reacts` are not built-in verbs. Without
    this, the declared-vocabulary test would pass just as happily against an
    implementation that recognised every alias it found."""
    root = tmp_path / "undeclared"
    doxyfile = _write_event_repo(root, "broadcasts", "reacts")

    assert _built_event_edges(root, doxyfile, tmp_path / "undeclared.db") == []
