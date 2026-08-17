# SPDX-License-Identifier: MIT
"""Layer 6: the declared indirect-dispatch recovery (tasks #60 / #30 / #35 / #37).

Three indirections hide one endpoint of a relationship, so the static graph
cannot see it: a virtual call through an injected interface (#35), a handler
reached through a function-pointer table (#30), and a shared key passed as an
ARGUMENT to a generic helper (#37). All three are CONVENTIONS, so recovery is
DECLARED — and a declaration is a claim about how the system is wired, which is
why every malformed shape here must refuse the build rather than quietly parse to
"declared nothing" and leave the author with a green build and the gap they were
closing still open.

Unit-level like the rest of the suite: hand-built doxygen-shaped databases
(memberdef / compounddef / member / reimplements / call_edges) plus synthetic
sources parsed by tree-sitter, no doxygen rebuild.

@brief Tests for clew.dispatch + clew.dispatch_edges.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.call_edges import build_call_edges
from clew.cli import _declared_or_flag
from clew.declaration import (
    DECLARATION_NAME,
    SECTION_DISPATCH,
    load_declaration,
)
from clew.dispatch import (
    empty_manifest,
    load_dispatch_manifest,
    shared_key_document,
)
from clew.dispatch_edges import import_declared_dispatch_edges
from clew.harvest import try_import_tree_sitter
from clew.shared_key_edges import (
    DEFAULT_SHARED_KEY_PATTERNS_VERSION,
    _inferred_cache_key,
    import_shared_key_edges_inferred,
)
from clew.treescan import manifest_key
from clew.vocabulary import (
    BOUNDARY_KIND_INTERFACE,
    BOUNDARY_STRENGTH_HIGH,
    CALL_MATCH_FUZZY,
    CALL_MATCH_RESOLVED,
    CALL_SOURCE_DECLARED_DISPATCH,
    DeclarationError,
)

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the dispatch-table harvest needs tree_sitter + its C/C++ grammars",
)

# ─── fixtures ────────────────────────────────────────────────────────────────

# A C++ codebase's HAL shape, reduced: a caller reaching hardware through an injected
# `hw::ILinkPort&`, one concrete implementor, and the DESTRUCTOR pair that made
# membership-only matching emit `ILinkPort::~ILinkPort -> ILinkPort::~ILinkPort`
# self-edges (doxygen lists a base's members under the derived compound too).
#
# EVERY IDENTIFIER IN THIS FILE IS INVENTED AND ILLUSTRATIVE. These fixtures
# reproduce the SHAPE of an indirection, never any real codebase's interface,
# method, helper or data-model-key names — do not go looking for them.
_IFACE_FUNCTIONS = [
    (10, "transmit", "void hw::ILinkPort::transmit(const Packet &pkt)", 1, 3),
    (11, "transmit", "void SerialLinkPort::transmit(const Packet &pkt)", 5, 8),
    (12, "emit_setpoint", "void StageDriver::emit_setpoint(int mm_s)", 10, 14),
    (13, "~ILinkPort", "hw::ILinkPort::~ILinkPort()", 16, 16),
]
_IFACE_COMPOUNDS = {
    # The interface is QUALIFIED in the index while the declaration names it
    # bare — the `%::Name` tail match is what bridges that.
    "hw::ILinkPort": [10, 13],
    # 10 and 13 are listed here too: doxygen registers a base class's inherited
    # members under the derived compound, with the BASE's rowids.
    "SerialLinkPort": [11, 10, 13],
    "StageDriver": [12],
}

_BROKER_SRC = """\
namespace demo {

void on_key(int key) { (void)key; }

void stage_shim(int key) { on_key(key); }

void Broker::fan(int key) { (void)key; }

void wire_up(Broker &b) { b.register_dispatcher(&stage_shim); }

}  // namespace demo
"""

_BROKER_FUNCTIONS = [
    (1, "on_key", "void demo::on_key(int key)", 3, 3),
    (2, "stage_shim", "void demo::stage_shim(int key)", 5, 5),
    (3, "fan", "void demo::Broker::fan(int key)", 7, 7),
    (4, "wire_up", "void demo::wire_up(Broker &b)", 9, 9),
]

# #37: the write half's key is an ARGUMENT (`DM_KEY_*` enum) to a generic helper,
# the read half's key is embedded in the accessor NAME. Neither the literal nor
# the name-embedded inference joins them without the declaration + the alias
# normalization the declaration turns on.
_WRAPPER_SRC = """\
void report_stall_state(int v) {
    store_bool_on_delta(DM_KEY_WIDGET_ENABLED, v);
}

int read_widget_enabled(void) {
    return DataModel_Get_WIDGET_ENABLED();
}
"""


## @brief Build a doxygen-shaped database for the declared-dispatch stage.
## @param tmp_path Test temp directory (also used as the repo root).
## @param functions (rowid, name, definition, bodystart, bodyend) tuples.
## @param compounds Compound name → the memberdef rowids `member` lists under it.
## @param reimplements (derived rowid, base rowid) pairs for doxygen's own relation.
## @param call_edges (caller rowid, callee rowid) non-fuzzy 'ast' rows.
## @param rel_path Indexed source path, relative to the repo root.
## @return Path to the created database.
## @version 1
def _make_db(
    tmp_path: Path,
    functions: list[tuple[int, str, str, int, int]],
    compounds: dict[str, list[int]] | None = None,
    reimplements: list[tuple[int, int]] | None = None,
    call_edges: list[tuple[int, int]] | None = None,
    rel_path: str = "src/broker.cpp",
    call_confidence: str = CALL_MATCH_RESOLVED,
) -> Path:
    """Uses the pipeline's OWN `build_call_edges` for the `call_edges` DDL, so the
    CHECK constraints and the UNIQUE key the stage's INSERT OR IGNORE relies on
    are the ones a real build ships rather than a hand-copied approximation.

    @brief Create a synthetic doxygen-shaped DB for the dispatch stage.
    @return The database path.
    @version 1
    """
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE xrefs (src_rowid INTEGER, dst_rowid INTEGER, context TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT);
        CREATE TABLE member (scope_rowid INTEGER, memberdef_rowid INTEGER);
        CREATE TABLE reimplements (memberdef_rowid INTEGER, reimplemented_rowid INTEGER);
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, ?)", (rel_path,))
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, file_id, bodyfile_id, "
        "bodystart, bodyend) VALUES (?, 'function', ?, ?, 1, 1, ?, ?)",
        functions,
    )
    for index, (name, members) in enumerate(sorted((compounds or {}).items()), start=1):
        conn.execute(
            "INSERT INTO compounddef (rowid, name, kind) VALUES (?, ?, 'class')", (index, name)
        )
        conn.executemany(
            "INSERT INTO member (scope_rowid, memberdef_rowid) VALUES (?, ?)",
            [(index, rowid) for rowid in members],
        )
    conn.executemany(
        "INSERT INTO reimplements (memberdef_rowid, reimplemented_rowid) VALUES (?, ?)",
        reimplements or [],
    )
    conn.commit()
    conn.close()

    build_call_edges(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, 'ast', ?)",
        [(caller, callee, call_confidence) for caller, callee in (call_edges or [])],
    )
    conn.commit()
    conn.close()
    return db_path


## @brief Every declared-dispatch call edge in a database.
## @param db_path Database to read.
## @return (caller, callee, confidence) rows, ordered.
## @version 1
def _declared_edges(db_path: Path) -> list[tuple[int, int, str]]:
    """@brief Read back only the rows this stage is allowed to have written."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT caller_rowid, callee_rowid, confidence FROM call_edges WHERE source = ? "
        "ORDER BY caller_rowid, callee_rowid",
        (CALL_SOURCE_DECLARED_DISPATCH,),
    ).fetchall()
    conn.close()
    return rows


## @brief Every terminus row in a database.
## @param db_path Database to read.
## @return (memberdef_rowid, global_name, kind, source, confidence) rows.
## @version 1
def _boundaries(db_path: Path) -> list[tuple]:
    """@brief Read back the external_boundaries rows, or [] when the table is absent."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT memberdef_rowid, global_name, kind, source, confidence "
            "FROM external_boundaries ORDER BY memberdef_rowid, global_name"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return rows


# ─── #35: interfaces ─────────────────────────────────────────────────────────


def test_declared_interface_binding_continues_the_chain_to_the_implementor(
    tmp_path: Path,
) -> None:
    """The whole point of #35. A virtual call DOES land on the interface method —
    it just stops there, so `StageDriver::emit_setpoint` reads as a zero-callee
    leaf even though its body crosses the HAL. Declaring the binding adds the
    sibling edge to the concrete override, and it carries the `declared_dispatch`
    provenance so a consumer can always ask whether the edge would exist without
    the manifest."""
    db = _make_db(
        tmp_path,
        _IFACE_FUNCTIONS,
        compounds=_IFACE_COMPOUNDS,
        reimplements=[(11, 10)],
        call_edges=[(12, 10)],
    )
    manifest = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "binds": "SerialLinkPort"}]}
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _declared_edges(db) == [(12, 11, CALL_MATCH_RESOLVED)]


def test_synthetic_edge_inherits_the_weakest_link_from_a_fuzzy_premise(
    tmp_path: Path,
) -> None:
    """A synthetic edge must never be more confident than the edge it was derived
    FROM. The premise here is a fuzzy incoming call: "a function of this name
    calls this interface method, though its class was never confirmed" (#48's
    `ast_member` case, which is mostly fuzzy by construction).

    The binding itself is unambiguous — exactly one override — so before the
    weakest-link rule this produced `resolved`, a high-confidence conclusion drawn
    from a low-confidence premise. That matters beyond provenance: BOTH the
    reachability BFS and thread membership traverse `resolved` and SKIP `fuzzy`,
    so an unverified premise would have propagated through the entire liveness
    graph as fact.

    Same fixture and same manifest as
    `test_declared_interface_binding_continues_the_chain_to_the_implementor`,
    which yields RESOLVED — the confidence of the incoming edge is the only
    difference between the two."""
    db = _make_db(
        tmp_path,
        _IFACE_FUNCTIONS,
        compounds=_IFACE_COMPOUNDS,
        reimplements=[(11, 10)],
        call_edges=[(12, 10)],
        call_confidence=CALL_MATCH_FUZZY,
    )
    manifest = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "binds": "SerialLinkPort"}]}
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _declared_edges(db) == [(12, 11, CALL_MATCH_FUZZY)]


def test_a_declared_boundary_is_recorded_even_from_a_fuzzy_call_site(tmp_path: Path) -> None:
    """The weakest-link rule governs synthetic CALL edges, not boundaries, and the
    asymmetry is deliberate. A boundary records the AUTHOR's claim that calls to
    this interface leave the repo — that claim does not become less true because
    one particular call site was resolved fuzzily, so `_boundary_rows` ignores
    incoming confidence while `_crossed_edges` respects it."""
    db = _make_db(
        tmp_path,
        _IFACE_FUNCTIONS,
        compounds=_IFACE_COMPOUNDS,
        reimplements=[(11, 10)],
        call_edges=[(12, 10)],
        call_confidence=CALL_MATCH_FUZZY,
    )
    manifest = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "binds": "SerialLinkPort", "boundary": True}]}
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _boundaries(db), "the declared boundary must survive a fuzzy call site"


def test_inherited_members_do_not_pair_the_interface_with_itself(tmp_path: Path) -> None:
    """doxygen lists a base class's members under the DERIVED compound too, with
    the BASE's rowids — so pairing on membership alone emits
    `ILinkPort::~ILinkPort -> ILinkPort::~ILinkPort`. The `definition`
    boundary filter is what keeps a compound's OWNED members only, and without it
    a declaration fabricates self-recursion on every inherited member."""
    db = _make_db(
        tmp_path,
        _IFACE_FUNCTIONS,
        compounds=_IFACE_COMPOUNDS,
        # No reimplements rows: force the same-name fallback, which is the path
        # that can see the inherited destructor as its own override.
        call_edges=[(12, 10), (12, 13)],
    )
    manifest = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "binds": "SerialLinkPort"}]}
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    edges = _declared_edges(db)
    assert (13, 13, CALL_MATCH_RESOLVED) not in edges
    assert all(caller != callee for caller, callee, _ in edges)
    # The same-name fallback still recovers the real override without doxygen's
    # reimplements relation (older doxygen, and C struct-of-fnptr "interfaces").
    assert (12, 11, CALL_MATCH_RESOLVED) in edges


def test_method_filter_narrows_the_binding(tmp_path: Path) -> None:
    """`methods:` restricts an entry to the named methods. A HAL interface whose
    implementor also overrides lifecycle members should be bindable on the one
    method that is the seam."""
    db = _make_db(
        tmp_path,
        _IFACE_FUNCTIONS,
        compounds=_IFACE_COMPOUNDS,
        call_edges=[(12, 10), (12, 13)],
    )
    manifest = load_dispatch_manifest(
        {
            "interfaces": [
                {
                    "interface": "ILinkPort",
                    "binds": "SerialLinkPort",
                    "methods": ["transmit"],
                }
            ]
        }
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _declared_edges(db) == [(12, 11, CALL_MATCH_RESOLVED)]


def test_boundary_flag_records_the_second_terminus_kind(tmp_path: Path) -> None:
    """`external_boundaries` recorded exactly ONE shape — a function pointer
    forwarded to an out-of-repo registrar — which is why an interface-HAL C++ codebase
    measured zero termini with the detector working correctly. `boundary: true`
    records the other shape: a virtual call whose implementor lives outside the
    index, which only the author can assert."""
    db = _make_db(tmp_path, _IFACE_FUNCTIONS, compounds=_IFACE_COMPOUNDS, call_edges=[(12, 10)])
    manifest = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "boundary": True}]}
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _boundaries(db) == [
        (
            12,
            "ILinkPort::transmit",
            BOUNDARY_KIND_INTERFACE,
            CALL_SOURCE_DECLARED_DISPATCH,
            BOUNDARY_STRENGTH_HIGH,
        )
    ]
    # A boundary-only entry declares no implementor, so it must add no call edge.
    assert _declared_edges(db) == []


def test_ambiguous_or_absent_class_is_skipped_not_guessed(tmp_path: Path) -> None:
    """Two indexed compounds sharing a tail would have DIFFERENT implementors, so
    picking one fabricates a call graph; and a declared type that is out of this
    build's scope (conditional compilation) must not fail a build, because a
    declaration is a standing statement across configurations."""
    compounds = dict(_IFACE_COMPOUNDS)
    compounds["other::ILinkPort"] = []
    db = _make_db(tmp_path, _IFACE_FUNCTIONS, compounds=compounds, call_edges=[(12, 10)])
    ambiguous = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "binds": "SerialLinkPort"}]}
    )
    import_declared_dispatch_edges(db, tmp_path, ambiguous)
    assert _declared_edges(db) == []

    absent = load_dispatch_manifest(
        {"interfaces": [{"interface": "INotIndexed", "binds": "AlsoAbsent"}]}
    )
    import_declared_dispatch_edges(db, tmp_path, absent)
    assert _declared_edges(db) == []


# ─── #30: dispatch tables ────────────────────────────────────────────────────


def test_declared_dispatch_table_connects_the_dispatcher_to_its_handlers(
    tmp_path: Path,
) -> None:
    """#30's shape, which Layer 4 structurally cannot reach: Layer 4 keys on a
    `GLOBAL = PARAM;` assignment, while a container-held pointer is registered by
    a METHOD CALL whose callee is a `field_expression` and whose argument is a
    `pointer_expression`. Declaring `register_via` + `dispatch_via` names both
    endpoints an edge needs, and the harvested registration site supplies the
    handler."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "broker.cpp").write_text(_BROKER_SRC, encoding="utf-8")
    db = _make_db(tmp_path, _BROKER_FUNCTIONS)
    manifest = load_dispatch_manifest(
        {
            "dispatch_tables": [
                {
                    "register_via": "register_dispatcher",
                    "handler_arg_index": 0,
                    "dispatch_via": "Broker::fan",
                }
            ]
        }
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    # `Broker::fan` (rowid 3) now reaches `stage_shim` (rowid 2), so the
    # membership and reachability BFS can flow across the seam.
    assert (3, 2, CALL_MATCH_RESOLVED) in _declared_edges(db)


def test_registration_site_is_harvested_but_is_not_itself_a_call_edge(
    tmp_path: Path,
) -> None:
    """`wire_up` STORES the handler; it does not invoke it. The registration site
    is what tells the stage which handler the table holds, but synthesizing
    `wire_up -> stage_shim` would assert a call that never happens, and
    an invented call edge is worse than a missing one — it feeds the same
    liveness and chain-trace surfaces a real edge does. Only the declared
    DISPATCHER gets the edge."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "broker.cpp").write_text(_BROKER_SRC, encoding="utf-8")
    db = _make_db(tmp_path, _BROKER_FUNCTIONS)
    manifest = load_dispatch_manifest(
        {
            "dispatch_tables": [
                {"register_via": "register_dispatcher", "dispatch_via": "Broker::fan"}
            ]
        }
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    edges = _declared_edges(db)
    assert edges == [(3, 2, CALL_MATCH_RESOLVED)]
    assert all(caller != 4 for caller, _callee, _conf in edges), (
        "the registrar's enclosing function must not be given a synthetic call edge"
    )


def test_unresolvable_dispatch_via_leaves_the_handlers_unconnected(tmp_path: Path) -> None:
    """A `dispatch_via` that resolves to no unique indexed function fails CLOSED:
    the handlers stay unconnected rather than being attributed to some other
    function, because attributing a whole dispatched sub-graph to the wrong
    caller is the one error here that is indistinguishable from a real graph."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "broker.cpp").write_text(_BROKER_SRC, encoding="utf-8")
    db = _make_db(tmp_path, _BROKER_FUNCTIONS)
    manifest = load_dispatch_manifest(
        {
            "dispatch_tables": [
                {"register_via": "register_dispatcher", "dispatch_via": "Absent::fan"}
            ]
        }
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _declared_edges(db) == []


def test_ambiguous_handler_name_records_NOTHING_rather_than_guessing(
    tmp_path: Path,
) -> None:
    """gh#347, reaching the DECLARED dispatch layer through the shared resolution helper — and
    it belongs here as much as in the ast layer. A dispatch manifest declares that a handler is
    registered; the handler is named at the registration SITE, so when that name matches two
    indexed functions the declaration has told us a dispatch exists and NOT which target it
    reaches. Emitting both asserted two dispatches where one was registered.

    THE OLD NAME SAID "degrades to fuzzy", which was a euphemism for "emits all of them".

    Its original reasoning is now stronger rather than discarded: it argued that fuzzy edges are
    skipped by the reachability BFS and thread membership, "so a guess cannot promote itself
    into the liveness answer". Under this rule there is no guess in the table at all, so the
    protection no longer depends on every downstream consumer remembering to filter — which is
    what `dossier`/`callers` failed to do (gh#26, three of four reported callers fabricated).

    WHAT IS DELIBERATELY LOST: a repo with two same-named handlers gets no declared-dispatch
    edge for that registration. That is the correct answer to "which one" being unknown, and the
    manifest can name the handler unambiguously if the author wants the edge."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "broker.cpp").write_text(_BROKER_SRC, encoding="utf-8")
    duplicated = [
        *_BROKER_FUNCTIONS,
        (5, "stage_shim", "void other::stage_shim(int key)", 20, 20),
    ]
    db = _make_db(tmp_path, duplicated)
    manifest = load_dispatch_manifest(
        {
            "dispatch_tables": [
                {"register_via": "register_dispatcher", "dispatch_via": "Broker::fan"}
            ]
        }
    )
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _declared_edges(db) == [], (
        "two same-named handlers means the target is unknown; one registration must not "
        "produce two dispatch edges"
    )


# ─── #37: argument-keyed shared-key wrappers ─────────────────────────────────


## @brief Build a db whose function bodies cover the wrapper source's lines.
## @param tmp_path Test temp directory (also the repo root).
## @return Path to the created database.
## @version 2
def _wrapper_db(tmp_path: Path) -> Path:
    """The shared-key pass resolves a harvested SITE LINE back to its enclosing
    function, so the body ranges — not just the names — have to match the source.

    @brief Create the #37 fixture database and its source file.
    @return The database path.
    @version 2
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dm.c").write_text(_WRAPPER_SRC, encoding="utf-8")
    return _make_db(
        tmp_path,
        [
            (1, "report_stall_state", "void report_stall_state(int v)", 1, 3),
            (2, "read_widget_enabled", "int read_widget_enabled(void)", 5, 7),
        ],
        rel_path="src/dm.c",
    )


## @brief Every shared-key edge in a database.
## @param db_path Database to read.
## @return (writer, reader, key_name) rows.
## @version 1
def _key_edges(db_path: Path) -> list[tuple[int, int, str]]:
    """@brief Read back the shared_key_edges rows, or [] when the table is absent."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT writer_rowid, reader_rowid, key_name FROM shared_key_edges "
            "ORDER BY writer_rowid, reader_rowid"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return rows


def test_declared_key_wrapper_produces_the_dataflow_edge(tmp_path: Path) -> None:
    """#37 end to end. The write half's key is an ARGUMENT to a generic helper and
    the read half's is embedded in the accessor NAME, so neither the literal nor
    the name-embedded inference joins them. Declaring the wrapper feeds the SAME
    Layer 5a matcher through `extra`, and the `DM_KEY_` alias normalization is
    what makes the two spellings of one key meet — without it the declaration
    yields an orphan write-half and no edge at all."""
    db = _wrapper_db(tmp_path)
    manifest = load_dispatch_manifest(
        {
            "shared_key_wrappers": [
                {"pattern": "store_bool_on_delta", "key_arg_index": 0, "direction": "write"}
            ]
        }
    )
    import_shared_key_edges_inferred(db, tmp_path, None, None, shared_key_document(manifest))

    assert _key_edges(db) == [(1, 2, "WIDGET_ENABLED")]


def test_without_the_declaration_the_same_dataflow_is_invisible(tmp_path: Path) -> None:
    """The correct negative that makes the previous test mean something: the
    built-in defaults see the name-embedded READ and nothing at all on the write
    side, so the key has no dataflow. The declaration is what closes it — not some
    pre-existing inference that would have fired anyway."""
    db = _wrapper_db(tmp_path)
    import_shared_key_edges_inferred(db, tmp_path, None, None, None)

    assert _key_edges(db) == []


def test_declared_wrapper_direction_selects_the_matcher_list(tmp_path: Path) -> None:
    """`direction` picks WHICH accessor list the wrapper joins. Filed as a READER,
    the same helper produces a read half with no write half to meet — so a typo'd
    direction would invert the dataflow the entry exists to reveal, which is
    exactly why the value is vocabulary-validated rather than defaulted."""
    db = _wrapper_db(tmp_path)
    manifest = load_dispatch_manifest(
        {
            "shared_key_wrappers": [
                {"pattern": "store_bool_on_delta", "key_arg_index": 0, "direction": "read"}
            ]
        }
    )
    import_shared_key_edges_inferred(db, tmp_path, None, None, shared_key_document(manifest))

    assert _key_edges(db) == []


def test_shared_key_document_is_none_when_nothing_contributes() -> None:
    """A manifest declaring only interfaces or tables must leave the shared-key
    stage's inputs — and therefore its cache key — completely untouched."""
    only_interfaces = load_dispatch_manifest({"interfaces": [{"interface": "I", "boundary": True}]})
    assert shared_key_document(only_interfaces) is None
    assert shared_key_document(empty_manifest()) is None


## @brief The #37 wrapper manifest, optionally declaring extra alias prefixes.
## @param prefixes Declared `key_alias_prefixes`, or None to declare none.
## @return The parsed dispatch manifest.
## @version 1
def _wrapper_manifest(prefixes: list[str] | None = None):
    """@brief Build the write-direction wrapper manifest used by the alias tests."""
    document: dict = {
        "shared_key_wrappers": [
            {"pattern": "store_bool_on_delta", "key_arg_index": 0, "direction": "write"}
        ]
    }
    if prefixes is not None:
        document["key_alias_prefixes"] = prefixes
    return load_dispatch_manifest(document)


def test_a_declared_alias_prefix_does_not_displace_the_ingot_default(tmp_path: Path) -> None:
    """REWRITTEN FOR gh#319, and the old contract is the point of the rewrite.

    This test used to be `..._replace_the_builtin_default` and asserted `[]` — that
    declaring `EXAMPLE_KEY_` KILLED the `DM_KEY_` normalization, so the write half
    became an orphan and no edge formed. It pinned as intended behaviour the one
    constant the gh#319 audit found combining wrongly.

    `DEFAULT_KEY_ALIAS_PREFIXES` is a TIER-4 known-ecosystem signature — the ingot
    generator's own enum prefix, not a guess about anyone's naming — so it
    accumulates and a declaration adds to it. That also makes it consistent with
    the writers and readers from the SAME generator, which have always accumulated.

    `DM_KEY_WIDGET_ENABLED` and `EXAMPLE_KEY_` are INVENTED. Provenance for an
    identifier in a public test is not decidable by reading it — a name lifted from
    a closed repo looks exactly like a name someone made up, which is why this
    project audits SHAPES rather than keeping a list of strings it must hide. The
    fixture only needs a prefix that is not the default.
    """
    db = _wrapper_db(tmp_path)
    import_shared_key_edges_inferred(
        db, tmp_path, None, None, shared_key_document(_wrapper_manifest(["EXAMPLE_KEY_"]))
    )

    assert _key_edges(db) == [(1, 2, "WIDGET_ENABLED")]


def test_a_declared_alias_prefix_still_normalizes_its_own_spelling(tmp_path: Path) -> None:
    """THE OTHER HALF, without which the test above passes on a build that ignores
    the declaration entirely.

    "The default survived" and "the declaration was honoured" are two claims, and
    accumulation is only demonstrated by both. Same fixture with the site keyed on
    `EXAMPLE_KEY_WIDGET_ENABLED` instead.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dm.c").write_text(
        _WRAPPER_SRC.replace("DM_KEY_WIDGET_ENABLED", "EXAMPLE_KEY_WIDGET_ENABLED"),
        encoding="utf-8",
    )
    db = _make_db(
        tmp_path,
        [
            (1, "report_stall_state", "void report_stall_state(int v)", 1, 3),
            (2, "read_widget_enabled", "int read_widget_enabled(void)", 5, 7),
        ],
        rel_path="src/dm.c",
    )
    import_shared_key_edges_inferred(
        db, tmp_path, None, None, shared_key_document(_wrapper_manifest(["EXAMPLE_KEY_"]))
    )

    assert _key_edges(db) == [(1, 2, "WIDGET_ENABLED")]


def test_an_undeclared_alias_spelling_is_not_normalized(tmp_path: Path) -> None:
    """THE NEGATIVE CONTROL for the pair above: without the declaration the
    `EXAMPLE_KEY_` site is NOT stripped, so the write half keys on
    `EXAMPLE_KEY_WIDGET_ENABLED`, never meets the reader's `WIDGET_ENABLED`, and no
    edge forms. Without this, the previous test could be passing because some other
    mechanism strips unknown prefixes.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dm.c").write_text(
        _WRAPPER_SRC.replace("DM_KEY_WIDGET_ENABLED", "EXAMPLE_KEY_WIDGET_ENABLED"),
        encoding="utf-8",
    )
    db = _make_db(
        tmp_path,
        [
            (1, "report_stall_state", "void report_stall_state(int v)", 1, 3),
            (2, "read_widget_enabled", "int read_widget_enabled(void)", 5, 7),
        ],
        rel_path="src/dm.c",
    )
    import_shared_key_edges_inferred(
        db, tmp_path, None, None, shared_key_document(_wrapper_manifest())
    )

    assert _key_edges(db) == []


# ─── fail closed ─────────────────────────────────────────────────────────────


def test_no_declaration_writes_nothing_at_all(tmp_path: Path) -> None:
    """The state every repo is in today. An undeclared repo has no indirection
    convention clew may assume, so zero synthetic rows is a correct negative —
    and every existing build must keep reproducing it exactly."""
    db = _make_db(tmp_path, _IFACE_FUNCTIONS, compounds=_IFACE_COMPOUNDS, call_edges=[(12, 10)])
    manifest = load_dispatch_manifest(None)
    assert manifest.is_empty()
    import_declared_dispatch_edges(db, tmp_path, manifest)

    assert _declared_edges(db) == []
    # Not even the terminus table is created: the stage returns before touching
    # the database at all.
    assert _boundaries(db) == []


def test_a_misspelled_section_refuses_the_build(tmp_path: Path) -> None:
    """The hole in the fail-closed promise, closed. An ABSENT section reads as
    "declared nothing", so every plausible singular/plural slip —
    `interface:`, `dispatch_table:`, `shared_key_wrapper:` — used to parse to an
    empty manifest and build GREEN while the author's declaration did nothing,
    which is indistinguishable from a repo that never declared anything."""
    for typo in ("interface", "dispatch_table", "shared_key_wrapper", "interfacs"):
        with pytest.raises(DeclarationError) as exc:
            load_dispatch_manifest({typo: [{"interface": "I", "boundary": True}]})
        message = str(exc.value)
        assert repr(typo) in message
        assert "interfaces" in message, "the error must name the allowed sections"


def test_a_misspelled_entry_field_refuses_the_build() -> None:
    """One level down, and worse than "declared nothing": `key_arg_idx` silently
    defaults the key to argument 0, so a typo does not produce NO dataflow, it
    produces the WRONG dataflow — a specific, real claim invented from a slip."""
    with pytest.raises(DeclarationError) as exc:
        load_dispatch_manifest({"shared_key_wrappers": [{"pattern": "w", "key_arg_idx": 2}]})
    assert "'key_arg_idx'" in str(exc.value)
    assert "key_arg_index" in str(exc.value)
    with pytest.raises(DeclarationError):
        load_dispatch_manifest({"interfaces": [{"interface": "I", "bind": "C"}]})
    with pytest.raises(DeclarationError):
        load_dispatch_manifest(
            {"dispatch_tables": [{"register_via": "r", "dispatch_via": "d", "handler": 0}]}
        )


def test_a_missing_required_endpoint_refuses_the_build() -> None:
    """There is no honest default for "which interface" or "which dispatcher" —
    inventing one binds a call graph the author never described. And an
    `interfaces:` entry with neither `binds` nor `boundary: true` asks for
    nothing, which is far more likely a half-finished edit than an intent."""
    with pytest.raises(DeclarationError, match="interface"):
        load_dispatch_manifest({"interfaces": [{"binds": "C"}]})
    with pytest.raises(DeclarationError, match="would do nothing"):
        load_dispatch_manifest({"interfaces": [{"interface": "I"}]})
    with pytest.raises(DeclarationError, match="dispatch_via"):
        load_dispatch_manifest({"dispatch_tables": [{"register_via": "r"}]})
    with pytest.raises(DeclarationError, match="pattern"):
        load_dispatch_manifest({"shared_key_wrappers": [{"direction": "write"}]})


def test_a_typod_direction_refuses_instead_of_filing_the_opposite_role() -> None:
    """A `direction` of 'wrtie' normalized to a reader would invert the dataflow
    the entry exists to reveal, and the build would still succeed. The message
    names the origin, the token and the full allowed set."""
    with pytest.raises(DeclarationError) as exc:
        load_dispatch_manifest({"shared_key_wrappers": [{"pattern": "w", "direction": "wrtie"}]})
    message = str(exc.value)
    assert ".clew.yaml [dispatch]" in message
    assert "'wrtie'" in message
    assert "write, read" in message


def test_a_section_that_is_not_a_list_of_mappings_refuses_the_build() -> None:
    """A section present but mis-SHAPED is a typo, not a declaration. Degrading it
    to "declared nothing" leaves the author with a green build and the gap they
    were closing still open."""
    for bad in ("ILinkPort", {"interface": "I"}, ["ILinkPort"], [None]):
        with pytest.raises(DeclarationError, match="must be a list of mappings"):
            load_dispatch_manifest({"interfaces": bad})


def test_a_standalone_manifest_file_and_a_declaration_section_share_one_parser(
    tmp_path: Path,
) -> None:
    """Both delivery routes converge on one parser, so `--dispatch` and the
    `.clew.yaml` `dispatch:` section are guaranteed to have exactly one format
    — and one set of error messages, which name the FILE when there is one."""
    path = tmp_path / "dispatch.yaml"
    path.write_text(
        "interfaces:\n  - interface: ILinkPort\n    binds: SerialLinkPort\n",
        encoding="utf-8",
    )
    from_file = load_dispatch_manifest(path)
    from_section = load_dispatch_manifest(
        {"interfaces": [{"interface": "ILinkPort", "binds": "SerialLinkPort"}]}
    )
    assert len(from_file.interfaces) == len(from_section.interfaces) == 1
    assert from_file.interfaces[0].binds == from_section.interfaces[0].binds

    bad = tmp_path / "bad.yaml"
    bad.write_text("interfaces:\n  - binds: OnlyThis\n", encoding="utf-8")
    with pytest.raises(DeclarationError) as exc:
        load_dispatch_manifest(bad)
    assert str(bad) in str(exc.value), "a file-sourced error must name the file to edit"


def test_the_declaration_route_reaches_the_stage_and_the_flag_wins(tmp_path: Path) -> None:
    """The reason a `dispatch:` section exists at all. The MCP server passes NO
    manifest arguments — the repo root is the only route it needs — so a convention
    reachable solely by CLI flag is invisible on the primary surface and the
    built-in defaults become the whole policy, which is precisely the
    hardcoded-only assumption the no-hardcoding mandate forbids. Discovery from
    the repo root is what closes that, and an explicit flag still wins because the
    file is a standing statement while the flag is a deliberate one-off."""
    (tmp_path / DECLARATION_NAME).write_text(
        "dispatch:\n  interfaces:\n    - interface: FromDeclaration\n      boundary: true\n",
        encoding="utf-8",
    )
    decl = load_declaration(tmp_path)
    assert SECTION_DISPATCH in decl

    from_declaration = load_dispatch_manifest(_declared_or_flag(None, decl, SECTION_DISPATCH))
    assert [b.interface for b in from_declaration.interfaces] == ["FromDeclaration"]

    override = tmp_path / "override.yaml"
    override.write_text(
        "interfaces:\n  - interface: FromFlag\n    boundary: true\n", encoding="utf-8"
    )
    from_flag = load_dispatch_manifest(_declared_or_flag(str(override), decl, SECTION_DISPATCH))
    assert [b.interface for b in from_flag.interfaces] == ["FromFlag"]

    # A repo declaring nothing reaches the stage with an empty manifest, not None.
    assert load_dispatch_manifest(_declared_or_flag(None, {}, SECTION_DISPATCH)).is_empty()


def test_the_dispatch_manifest_participates_in_the_stage_cache_key(tmp_path: Path) -> None:
    """The declaration decides what the per-file registration harvest MATCHES, so
    editing it has to re-harvest. A manifest that did not reach the cache key
    would leave a stale payload in place and the edit would appear to do nothing —
    the same class of silent failure as a dropped declaration."""
    one = load_dispatch_manifest({"shared_key_wrappers": [{"pattern": "a", "key_arg_index": 0}]})
    two = load_dispatch_manifest({"shared_key_wrappers": [{"pattern": "a", "key_arg_index": 1}]})
    assert manifest_key(shared_key_document(one)) != manifest_key(shared_key_document(two))
    # An undeclared build must keep the exact key it had before this parameter
    # existed, so no existing cache is invalidated by the merge point alone.
    assert _inferred_cache_key(None, None) == DEFAULT_SHARED_KEY_PATTERNS_VERSION
    assert _inferred_cache_key(None, shared_key_document(one)) != _inferred_cache_key(None, None)


def test_a_manifest_file_that_is_not_a_mapping_refuses_the_build(tmp_path: Path) -> None:
    """@brief A YAML list (or scalar) where a mapping belongs is refused."""
    path = tmp_path / "dispatch.yaml"
    path.write_text("- interface: ILinkPort\n", encoding="utf-8")
    with pytest.raises(DeclarationError, match="must contain a mapping"):
        load_dispatch_manifest(path)
