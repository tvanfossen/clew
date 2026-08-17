# SPDX-License-Identifier: MIT
"""gh#8 — doxygen's `reimplements` relation, made reachable.

The relation was populated on every C++ build and read by exactly one module,
`dispatch_edges.py`. `grep -rln reimplement clew/` matched that file and
nothing in `query/` or `mcp_server/`, so a consumer could not ask what a virtual
call actually runs. A benchmark mark rewarding exactly that observation missed 9
of 9 cells across all three model tiers — as did the source arm, which cannot
read a database table at all. A mark missed uniformly by every model on every run
is a missing capability.

THE FIXTURE PLANTS THE RELATION AGAINST THE DECLARATION ROWID, deliberately.
`sensor_poll` is memberdef 76 (definition) and 158 (header declaration), and the
dossier resolves to 76. Recording the relation against 158 only is the decl/def
duality in the position where it actually bites: a lookup keyed on the reported
rowid finds nothing, and one keyed on the IDENTITY finds it. Every override test
here would pass on a rowid-keyed implementation if the relation were planted
against 76, which is why it is not.

@brief Tests for the override/reimplements query surface (gh#8).
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew import query as q

## The fixture's decl/def pair for `sensor_poll`: 76 defines it, 158 declares it in
## the header. Kept as named constants because the whole point of the fixture is that
## these two rowids are the SAME function and a bare number does not say so.
SENSOR_POLL_DEF = 76
SENSOR_POLL_DECL = 158
## Two unrelated indexed functions standing in for concrete overrides. Invented roles,
## real rowids — see tests/richdb.py on why the numbers are the ones a real build gave.
TELEMETRY_REPORT = 75
HANDLE_CLOUD_COMMAND = 37


## @brief A writable copy of the shared index with a planted override relation.
## @param rich_db The session-scoped read-only index.
## @param tmp_path Per-test temporary directory.
## @return Path to the copy.
## @version 1
@pytest.fixture()
def overriding_db(rich_db: Path, tmp_path: Path) -> Path:
    """Two functions "reimplement" `sensor_poll`, recorded against its DECLARATION
    rowid. `rich_db` is session-scoped and shared, so this works on a byte copy.

    @brief Index carrying a two-implementor override relation.
    @return Path to a writable clew.db.
    @version 1
    """
    own = tmp_path / "clew.db"
    shutil.copy(rich_db, own)
    conn = sqlite3.connect(own)
    try:
        conn.executemany(
            "INSERT INTO reimplements (memberdef_rowid, reimplemented_rowid) VALUES (?,?)",
            [(TELEMETRY_REPORT, SENSOR_POLL_DECL), (HANDLE_CLOUD_COMMAND, SENSOR_POLL_DECL)],
        )
        conn.commit()
    finally:
        conn.close()
    return own


def test_a_dossier_on_an_overridden_function_names_its_implementors(overriding_db: Path) -> None:
    """gh#8's "done means", asserted: a consumer can answer "what runs here?".

    Both implementors are named, with the location and signature that let the consumer
    go and read one — the point of returning a ref rather than a bare name. And the
    relation is found despite being recorded against the declaration while the dossier
    describes the definition, which is the identity resolution doing its job.
    """
    doss = q.function_dossier(overriding_db, "sensor_poll")
    assert doss is not None
    assert doss.rowid == SENSOR_POLL_DEF, "the dossier describes the definition row"

    named = {o.name for o in doss.overridden_by}
    assert named == {"telemetry_report", "handle_cloud_command"}
    for ref in doss.overridden_by:
        assert ref.rowid > 0
        assert ref.file, "an implementor must be locatable without a second lookup"
        assert ref.signature, "the signature is what distinguishes same-named overrides"


def test_the_two_directions_are_not_the_same_question(overriding_db: Path) -> None:
    """`overrides` and `overridden_by` must not be each other.

    A single relation table read in one direction only is the easy mistake here, and it
    would present a base method as overriding its own implementors. The base's
    `overrides` is EMPTY (it reimplements nothing) while an implementor's names it —
    asserted on the same database so a symmetric bug cannot satisfy both halves.
    """
    base = q.function_dossier(overriding_db, "sensor_poll")
    impl = q.function_dossier(overriding_db, "telemetry_report")
    assert base is not None
    assert impl is not None

    assert base.overrides == [], "the base method reimplements nothing"
    assert len(base.overridden_by) == 2

    assert {o.name for o in impl.overrides} == {"sensor_poll"}
    assert impl.overridden_by == [], "nothing reimplements the leaf implementor"


def test_a_non_virtual_function_gets_no_override_fields(rich_db: Path) -> None:
    """No spurious polymorphism on the ordinary case, which is almost every function.

    Asserted on the UNMODIFIED fixture, whose `reimplements` table exists and is empty
    — the state a C or Python target is permanently in. Both fields are `[]`, which is
    the measurement "doxygen recorded no override relation", and no call edge claims an
    implementor.
    """
    doss = q.function_dossier(rich_db, "sensor_poll")
    assert doss is not None
    assert doss.overrides == []
    assert doss.overridden_by == []
    assert all(edge.implementors == () for edge in doss.callers + doss.callees)


def test_a_call_to_an_overridden_endpoint_is_annotated_with_its_implementors(
    overriding_db: Path,
) -> None:
    """The `callees` half of gh#8 — and the two things it must NOT do.

    `app_run` calls `sensor_poll`, which the fixture makes virtual, so that edge names
    the bodies the dispatch can reach. What it must not do is UPGRADE the edge or ADD
    one: `confidence` still grades the call itself, and the neighbour count is
    unchanged, because this repo's rule is that a synthetic edge inherits the weakest
    link and the honest way to respect that is to annotate rather than to mint.
    """
    plain = {(e.name, e.confidence) for e in q.callees(rich_db_of(overriding_db), "app_run")}
    annotated = q.callees(overriding_db, "app_run")

    edge = next(e for e in annotated if e.name == "sensor_poll")
    assert set(edge.implementors) == {"telemetry_report", "handle_cloud_command"}
    # Every OTHER neighbour is untouched, and no neighbour was gained or lost.
    assert {(e.name, e.confidence) for e in annotated} == plain
    assert all(e.implementors == () for e in annotated if e.name != "sensor_poll")


## @brief The same index with its override relation removed, for a control comparison.
## @param db Database carrying planted override rows.
## @return Path to a copy with `reimplements` emptied.
## @version 1
def rich_db_of(db: Path) -> Path:
    """The CONTROL for the test above. Comparing an annotated neighbour list against a
    hand-written expectation would let an added or dropped edge pass unnoticed, so the
    comparison is against the SAME database with only the relation deleted — one
    variable.

    Written as a helper rather than a fixture because it is derived from another
    fixture's output, and a fixture depending on a fixture depending on a session
    fixture is harder to read than four lines.

    @brief A copy of `db` with no override rows.
    @return Path to the control database.
    @version 1
    """
    control = db.parent / "control.db"
    shutil.copy(db, control)
    conn = sqlite3.connect(control)
    try:
        conn.execute("DELETE FROM reimplements")
        conn.commit()
    finally:
        conn.close()
    return control


def test_an_index_without_the_relation_degrades_to_empty(overriding_db: Path) -> None:
    """`reimplements` is DOXYGEN'S table, not ours — we copy the file doxygen wrote.

    So its absence means the index predates that output, and the surface must return
    empty rather than raising: an override query is exactly the kind a consumer runs
    against an old index while investigating why an answer looks thin.
    """
    conn = sqlite3.connect(overriding_db)
    try:
        conn.execute("DROP TABLE reimplements")
        conn.commit()
    finally:
        conn.close()

    doss = q.function_dossier(overriding_db, "sensor_poll")
    assert doss is not None
    assert doss.overrides == []
    assert doss.overridden_by == []
    assert all(e.implementors == () for e in q.callees(overriding_db, "app_run"))


def test_the_override_fields_reach_the_mcp_wire(overriding_db: Path, repo_root: Path) -> None:
    """gh#8 END TO END, because the query layer is not the surface a model sees.

    Two elision rules meet here and they pull opposite ways. `overrides` /
    `overridden_by` are ENVELOPE keys, so they survive at `[]` and a consumer can read
    "no override recorded" without guessing. `implementors` is a field of a ROW, so it
    is elided when empty — which is correct and is why the assertion checks the
    ANNOTATED row rather than merely that the key exists somewhere.

    An empty `implementors` shipping as `[]` on every one of a hub symbol's neighbours
    would be pure noise; an absent `overrides` on a dossier would be a question the
    caller has to ask again.
    """
    pytest.importorskip("mcp", reason="MCP server is an optional extra")
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: overriding_db, lambda: repo_root)

    doss = tools.dossier("sensor_poll")
    assert doss["overrides"] == [], "an envelope key survives at empty"
    assert {o["name"] for o in doss["overridden_by"]} == {
        "telemetry_report",
        "handle_cloud_command",
    }

    ## Read off `dossier`'s own `callees` since gh#372 folded the neighbour tools into it.
    ## The rows are the same rows, which is exactly the claim that fold rests on — and
    ## `implementors` is the field most able to be lost in a re-serialization, because it
    ## is a ROW field that is elided when empty.
    callees = tools.dossier("app_run")["callees"]
    edge = next(e for e in callees if e["name"] == "sensor_poll")
    assert set(edge["implementors"]) == {"telemetry_report", "handle_cloud_command"}
    others = [e for e in callees if e["name"] != "sensor_poll"]
    assert others, "the control needs at least one unannotated neighbour"
    assert all("implementors" not in e for e in others), (
        "an empty implementors list is a ROW field and must be elided, not shipped"
    )


def test_the_override_surface_is_reachable_from_the_package(overriding_db: Path) -> None:
    """Exported, because "populated and unreachable" was the whole defect.

    The accessors are also usable directly, not only through `dossier`: a consumer that
    already has a name and wants only the dispatch answer should not have to compose a
    whole dossier for it.
    """
    assert "overrides_of" in q.__all__
    assert "overridden_by" in q.__all__
    assert "OverrideRef" in q.__all__

    conn = sqlite3.connect(overriding_db)
    try:
        assert {o.name for o in q.overridden_by(conn, "sensor_poll")} == {
            "telemetry_report",
            "handle_cloud_command",
        }
        assert q.overrides_of(conn, "sensor_poll") == []
    finally:
        conn.close()
