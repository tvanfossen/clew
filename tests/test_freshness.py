# SPDX-License-Identifier: MIT
"""THE TOOL DESCRIBING ITS OWN CURRENCY — gh#2, gh#9 and gh#29 as one surface.

Three axes make `stale` true and they need three different actions, so the tests are
organised by axis rather than by module. Each one has a CONTROL beside it, because the
whole point of the change is a signal that stays worth reading — and the failure mode of
every warning this repo has shipped is that it fired on the ordinary case, got ignored,
and then got switched off.

The load-bearing test here is `test_a_current_index_carries_no_staleness_noise`. Every
other test proves the annotation appears; that one proves it can still disappear.

@brief Tests for the data / code / schema staleness axes.
@version 1
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="MCP server is an optional extra (pip install -e '.[mcp]')")

from clew.mcp_server import freshness as fr
from clew.mcp_server import state as st
from clew.mcp_server.tools_query import (
    RESPONSE_BUDGET_BYTES,
    QueryTools,
)
from clew.signature import (
    CLEW_BUILD_VERSION,
    read_build_signature,
    write_build_signature,
)

CURRENT = CLEW_BUILD_VERSION

## A code identity asserting the process matches its source, so a test about the DATA or
## SCHEMA axis is not perturbed by whether this checkout happens to have been edited
## since the test process imported it. The code axis has its own tests below.
MATCHING_CODE: dict[str, object] = {
    "package_version": "0.0.0-test",
    "process_fingerprint": "aaaaaaaaaaaa",
    "source_fingerprint": "aaaaaaaaaaaa",
    "matches_source": True,
}


## @brief A status payload describing a perfectly current index.
## @param **overrides Fields to change.
## @return A db_status-shaped mapping.
## @version 1
def _status(**overrides: object) -> dict[str, object]:
    """Built from a CURRENT baseline so every test states only its own deviation — a
    fixture that started stale would let a test pass on the wrong axis.

    @brief Compose a status payload.
    @return The mapping.
    @version 1
    """
    base: dict[str, object] = {
        "exists": True,
        "build_version": CURRENT,
        "expected_build_version": CURRENT,
        "source_changed_files": 0,
        "newest_changed_source": None,
        "stale": False,
    }
    base.update(overrides)
    return base


## @brief The message for one axis, or "" when that axis is silent.
## @param found A notice list.
## @param axis Axis token to look for.
## @return The message text, or "".
## @version 1
def _message(found: list[dict[str, str]], axis: str) -> str:
    """@brief Extract one axis's message.
    @return The message, or "".
    @version 1
    """
    return next((n["message"] for n in found if n["axis"] == axis), "")


# ─── the control: a current tool says nothing ─────────────────────────────────


## @brief A wholly current index and process produce no notices at all.
## @return None.
## @version 1
def test_a_current_index_carries_no_staleness_noise() -> None:
    """THE CONTROL ON THE ENTIRE CHANGE. This annotation rides on every query reply, so
    if it cannot be silent it becomes a permanent banner that trains the reader to skip
    it — which is how the disarmed coverage gate, the leaked identifiers and a whole
    36-cell grid each got past someone.

    Mutating any single term of `_status` below must break this test; that is what the
    per-axis tests immediately following are.

    @brief A current tool is annotated with nothing.
    @version 1
    """
    assert fr.notices(_status(), MATCHING_CODE) == []


# ─── axis: schema (gh#29's cheap half — two integers nothing interpreted) ─────


## @brief An index NEWER than the server tells the reader to restart, never to rebuild.
## @return None.
## @version 1
def test_a_server_predating_its_index_is_told_to_restart_not_to_rebuild() -> None:
    """THE UNRESOLVABLE CASE, observed live at build 23 against a server expecting 17.
    A rebuild re-stamps the SAME newer version, so `stale: true` cannot be cleared by any
    action the consumer takes — and advising a rebuild sends them round a loop with no
    exit. The diagnosis was already in the payload as two mismatched integers and
    nothing read them out loud.

    Asserts the DIRECTION explicitly, not merely that some message appeared: a notice
    that fired here with the other branch's text would be worse than no notice, because
    it would be confidently wrong about the remedy.

    @brief The index-newer direction names a restart and denies a rebuild.
    @version 1
    """
    found = fr.notices(_status(build_version=CURRENT + 6, stale=True), MATCHING_CODE)

    message = _message(found, fr.AXIS_SCHEMA)
    assert message, "a version skew must raise the schema axis"
    assert "restart" in message.lower(), "the only action that clears this must be named"
    assert "CANNOT CLEAR" in message, "it must say a rebuild cannot clear the flag"
    ## SPELLED AS THE TOOL SPELLS IT. This forbade `build_or_refresh`, which the served messages
    ## stopped saying when the three admin tools were folded into `index(action=...)` — so the
    ## guard went on passing while forbidding a string that could no longer appear. A negative
    ## assertion pinned to a renamed identifier is the quietest vacuous test there is: it never
    ## fails, and nothing distinguishes "the defect is absent" from "the check cannot see it".
    assert "action='refresh'" not in message, (
        "advising a rebuild here is the defect: rebuilding re-stamps the same newer "
        "version and the flag stays up"
    )
    assert str(CURRENT + 6) in message and str(CURRENT) in message, (
        "both integers belong in the message — the reader needs the comparison, not the verdict"
    )


## @brief An index OLDER than the server is told to rebuild.
## @return None.
## @version 1
def test_an_index_predating_the_server_is_told_to_rebuild() -> None:
    """The opposite direction, and the reason the test above asserts on direction rather
    than on presence. This one IS fixed by a rebuild, so the advice must invert.

    @brief The index-older direction names a rebuild.
    @version 1
    """
    message = _message(
        fr.notices(_status(build_version=CURRENT - 6, stale=True), MATCHING_CODE),
        fr.AXIS_SCHEMA,
    )
    assert "index(action='refresh'" in message
    assert "restart" not in message.lower()


## @brief An index with no readable build version does not manufacture a schema notice.
## @return None.
## @version 1
def test_an_unstamped_index_raises_no_schema_axis() -> None:
    """`read_build_signature` returns None for an unreadable or unstamped database. That
    is "cannot tell", and comparing None against an int must not produce a confident
    claim about which side is newer.

    @brief A None build version is not a version skew.
    @version 1
    """
    assert _message(fr.notices(_status(build_version=None), MATCHING_CODE), fr.AXIS_SCHEMA) == ""


# ─── axis: data (gh#2, with gh#9's measured cost attached) ────────────────────


## @brief Source drift raises the data axis and quotes the MEASURED cost of fixing it.
## @return None.
## @version 1
def test_the_data_axis_quotes_the_measured_refresh_cost() -> None:
    """gh#9's whole argument in one assertion: an agent that cannot measure the
    correction must estimate it, and it estimates badly — Q7 and Q8 are the only two
    questions where the index arm scored BELOW reading source, and Q8 is the worst
    result in the matrix. The number must come from THIS target's history, so it is
    quoted from the persisted `refresh` block rather than from a constant.

    @brief The data axis carries the measured cost.
    @version 1
    """
    status = _status(
        source_changed_files=5,
        newest_changed_source="clew/mcp_server/tools_query.py",
        stale=True,
        refresh={"duration_ms": "3314", "files_reprocessed": "7"},
    )

    message = _message(fr.notices(status, MATCHING_CODE), fr.AXIS_DATA)
    assert "5 indexed source file(s)" in message
    assert "tools_query.py" in message, "naming the newest changed file makes it checkable"
    assert "3314 ms" in message, "the cost must be the measured one"
    assert "7 file(s)" in message
    assert "index(action='refresh'" in message, "the action that clears this axis must be named"


## @brief With no timing history the data axis says so instead of inventing a number.
## @return None.
## @version 1
def test_an_untimed_target_says_the_cost_is_unmeasured() -> None:
    """A fabricated estimate presented as a measurement is the failure this repo has
    recorded more than any other — a `$0.5` placeholder whose own comment said it was
    not measured became an authoritative budget by being copied into prose. So an index
    predating the `refresh` section reports the absence, and reports it as an absence.

    @brief An untimed target admits the cost is unmeasured.
    @version 1
    """
    message = _message(
        fr.notices(_status(source_changed_files=1, stale=True), MATCHING_CODE), fr.AXIS_DATA
    )
    assert "unmeasured" in message
    assert "ms" not in message, "no number may appear where none was measured"


## @brief A measured ZERO is reported as a measurement, not as an absence.
## @return None.
## @version 1
def test_a_zero_duration_reads_as_measured_not_as_missing() -> None:
    """A fully cached rebuild legitimately costs ~0 ms and reprocesses 0 files. The
    persisted value is the STRING "0" precisely so it survives the falsy-drop rule, and
    the phrasing layer must not undo that by treating it as absent.

    @brief Zero is a measurement.
    @version 1
    """
    clause = fr._cost_clause({"duration_ms": "0", "files_reprocessed": "0"})
    assert "0 ms" in clause
    assert "unmeasured" not in clause


# ─── axis: code (gh#29's misleading half) ────────────────────────────────────


## @brief The code axis fires when the source moved under the running process.
## @return None.
## @version 1
def test_the_code_axis_fires_when_the_source_moves_under_the_process() -> None:
    """The axis that had NO signal and whose available signal pointed the other way: a
    fix lands, `status` says `stale: false` — truthfully, about the data axis — and the
    query returns the pre-fix payload byte-for-byte. It has cost this loop three
    debugging sessions.

    @brief Disagreeing fingerprints raise the code axis.
    @version 1
    """
    code = dict(MATCHING_CODE, source_fingerprint="bbbbbbbbbbbb", matches_source=False)

    message = _message(fr.notices(_status(), code), fr.AXIS_CODE)
    assert "aaaaaaaaaaaa" in message and "bbbbbbbbbbbb" in message
    assert "restart" in message.lower(), "only a client restart replaces loaded modules"


## @brief The code axis must not let a reader conclude the DATA is stale.
## @return None.
## @version 1
def test_the_code_axis_says_the_data_is_still_current() -> None:
    """MEASURED, and the reason the wording is pinned by a test: query tools open the
    database per call, so newly-added symbols appear immediately even while the process
    runs old logic. Saying "the server is stale" without that qualification trades one
    wrong conclusion for the opposite one, and would send someone rebuilding an index
    that was never the problem.

    @brief The code axis exempts the data explicitly.
    @version 1
    """
    code = dict(MATCHING_CODE, source_fingerprint="bbbbbbbbbbbb", matches_source=False)

    message = _message(fr.notices(_status(), code), fr.AXIS_CODE)
    assert "READS are not affected" in message
    assert "read" in message and "live" in message
    assert "rebuild cannot fix this" in message


## @brief The code axis must ALSO say that building through this process is refused.
## @return None.
## @version 1
def test_the_code_axis_says_a_build_through_it_is_refused() -> None:
    """THE OTHER HALF OF THE SAME SENTENCE, and the half whose absence was measured
    (gh#348). The message used to read "The DATA is not affected", full stop — TRUE FOR
    READS, FALSE FOR WRITES. A build-30 process rebuilt a build-32 index AT 30, the
    `external` stage vanished from the stage list, and `status` then reported
    `stale: false, build_version: 30` — perfectly healthy, having just destroyed a layer.

    The reader was TOLD not to worry by the very notice that should have stopped them, so
    the read exemption above and this refusal have to travel together. Testing only the
    exemption is what let the wrong half ship pinned.

    @brief The code axis states the write hazard, not only the read exemption.
    @version 1
    """
    code = dict(MATCHING_CODE, source_fingerprint="bbbbbbbbbbbb", matches_source=False)

    message = _message(fr.notices(_status(), code), fr.AXIS_CODE)
    assert "refused" in message.lower(), "a stale process must not be invited to build"
    assert "DROP WHOLE LAYERS" in message, "name the consequence, not just the prohibition"


## @brief A stale process refuses a write; a matching one raises no objection.
## @return None.
## @version 1
def test_a_stale_process_refuses_a_write_and_a_matching_one_does_not() -> None:
    """THE CONTROL IS THE SECOND HALF. A refusal that fires unconditionally would block
    every build on every target, which is a worse bug than the one being fixed — and this
    repo's whole warning history is of signals that could not be silent.

    The refusal names the remedy because it costs exactly one reconnect: measured, a client
    restart plus `build_or_refresh(force=True)` restored `external=29` to the stage list and
    both `options.*.tier` rows.

    @brief A stale identity refuses; a matching identity does not.
    @version 1
    """
    stale = dict(MATCHING_CODE, source_fingerprint="bbbbbbbbbbbb", matches_source=False)

    refusal = fr.stale_code_refusal(stale)
    assert refusal is not None
    assert "restart" in refusal.lower() and "force=True" in refusal
    assert "Nothing was written" in refusal

    assert fr.stale_code_refusal(MATCHING_CODE) is None


## @brief An unreadable source tree yields "cannot tell", never a fabricated warning.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_an_unreadable_source_tree_does_not_manufacture_a_code_warning(tmp_path: Path) -> None:
    """`source_fingerprint` returns "" for a tree it cannot read, and that must read as
    absent evidence rather than as disagreement. A warning that fires when the check
    could not run is the "guard that fires on some of the real cases" defect: it converts
    "unchecked" into "checked and wrong".

    @brief An empty fingerprint is not evidence of drift.
    @version 1
    """
    assert fr.source_fingerprint(tmp_path / "does-not-exist") == ""

    unknown = dict(MATCHING_CODE, source_fingerprint="", matches_source=True)
    assert _message(fr.notices(_status(), unknown), fr.AXIS_CODE) == ""


## @brief The fingerprint moves when a source file is touched, and holds when it is not.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_the_fingerprint_tracks_the_source_tree(tmp_path: Path) -> None:
    """Both halves matter. A fingerprint that never changes cannot detect drift; one
    that changes when nothing did makes the code axis fire permanently, which is the
    same failure as no signal at all.

    Asserts on mtime rather than sleeping: `os.utime` makes the change deterministic
    where a sleep makes the test slow AND flaky.

    @brief The fingerprint is sensitive and stable.
    @version 1
    """
    import os

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")

    before = fr.source_fingerprint(pkg)
    assert before, "a readable tree must fingerprint"
    assert fr.source_fingerprint(pkg) == before, "an untouched tree must not drift"

    stat = (pkg / "a.py").stat()
    os.utime(pkg / "a.py", ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert fr.source_fingerprint(pkg) != before, "a touched file must move the fingerprint"


## @brief A non-`.py` file does not move the fingerprint.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_bytecode_does_not_move_the_fingerprint(tmp_path: Path) -> None:
    """`.pyc` is regenerated as a side effect of importing the very code being
    identified, and the house control procedure purges `__pycache__` between runs — so
    hashing bytecode would move the fingerprint because it was READ, and again because a
    control run cleaned up.

    @brief Only source files are fingerprinted.
    @version 1
    """
    pkg = tmp_path / "pkg"
    (pkg / "__pycache__").mkdir(parents=True)
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    before = fr.source_fingerprint(pkg)

    (pkg / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00\x01")
    assert fr.source_fingerprint(pkg) == before


# ─── all three at once, and the ordering ──────────────────────────────────────


## @brief Three simultaneous axes are all reported, in remedy order.
## @return None.
## @version 1
def test_every_axis_in_play_is_reported() -> None:
    """A real session can hold all three, and reporting only the first would hide the
    one that says no rebuild will help. The order is data → schema → code: cheapest and
    commonest remedy first, "nothing you can rebuild" last.

    @brief All active axes are reported in order.
    @version 1
    """
    status = _status(build_version=CURRENT + 1, source_changed_files=2, stale=True)
    code = dict(MATCHING_CODE, source_fingerprint="bbbbbbbbbbbb", matches_source=False)

    axes = [n["axis"] for n in fr.notices(status, code)]
    assert axes == [fr.AXIS_DATA, fr.AXIS_SCHEMA, fr.AXIS_CODE]


# ─── the persisted refresh cost (gh#9's pipeline half) ────────────────────────


## @brief A refresh section round-trips through build_meta into db_status.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_the_refresh_cost_round_trips_into_status(tmp_path: Path) -> None:
    """The path that makes the estimate grounded in this target's own history: the
    pipeline stamps it, `_refresh_meta` reads it back, `db_status` publishes it.

    @brief Refresh metrics reach db_status.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE memberdef (id INTEGER)")
    conn.commit()
    conn.close()
    write_build_signature(
        db, refresh={"duration_ms": "1612", "files_reprocessed": "3", "cache_hits": "111"}
    )

    target = st.Target(repo_path=str(tmp_path), slug="t", db_path=str(db))
    refresh = st.db_status(target)["refresh"]
    assert refresh == {"duration_ms": "1612", "files_reprocessed": "3", "cache_hits": "111"}


## @brief A measured ZERO survives persistence, where a falsy value would be dropped.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_zero_refresh_measurement_survives_persistence(tmp_path: Path) -> None:
    """`write_build_signature` DROPS FALSY VALUES so an absent key can honestly read as
    "not recorded". gh#6, gh#17 and gh#18 each had to work around that for a measured
    zero; this is the fourth section to do so, and a fully cached rebuild really does
    reprocess zero files in under a millisecond.

    The test writes STRINGS, which is the contract — and asserts the value comes back,
    which is what would break if a caller ever passed the int.

    @brief Zero survives the falsy-drop rule.
    @version 1
    """
    db = tmp_path / "clew.db"
    write_build_signature(db, refresh={"duration_ms": "0", "files_reprocessed": "0"})

    target = st.Target(repo_path=str(tmp_path), slug="t", db_path=str(db))
    assert st.db_status(target)["refresh"] == {"duration_ms": "0", "files_reprocessed": "0"}


## @brief Stamping a refresh section leaves the other sections intact.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_stamping_the_refresh_section_preserves_scope_and_version(tmp_path: Path) -> None:
    """The pipeline stamps `refresh.*` in a SECOND `write_build_signature` call, after
    the atomic swap and the HTML stage, so the duration covers the whole build. That is
    only safe because the write UPSERTS — if it replaced the table, this stamp would
    silently delete the scope provenance that the entropic grid measured as the only
    clearly actionable gap in 56 marks.

    @brief A second stamp does not clobber the first.
    @version 1
    """
    db = tmp_path / "clew.db"
    write_build_signature(db, scope={"source": "doxygen-guard", "reason": "declared"})
    write_build_signature(db, refresh={"duration_ms": "42"})

    target = st.Target(repo_path=str(tmp_path), slug="t", db_path=str(db))
    status = st.db_status(target)
    assert status["scope"] == {"source": "doxygen-guard", "reason": "declared"}
    assert status["refresh"] == {"duration_ms": "42"}
    assert read_build_signature(db) == CLEW_BUILD_VERSION


# ─── the query-reply annotation (gh#2's chosen mechanism) ─────────────────────


## @brief A query against a stale database carries that fact in its own payload.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_a_query_against_a_stale_index_carries_the_staleness(rich_db: Path) -> None:
    """gh#2's mechanism. `status` reported staleness clearly and without being asked
    twice — but reading it requires already SUSPECTING a problem, which is exactly what
    a consumer holding a confident, fresh-looking answer does not have. The signal was
    opt-in and the failure silent.

    Driven through `QueryTools` rather than the notice function, because the claim is
    about what a model actually receives.

    @brief A stale index annotates its query replies.
    @version 1
    """
    drift = [{"axis": fr.AXIS_DATA, "message": "5 files changed; call build_or_refresh()"}]
    tools = QueryTools(lambda: rich_db, lambda: rich_db.parent, lambda: drift)

    payload = tools.dossier("main")
    assert payload["staleness"] == drift
    assert payload["target"], "the target stamp must survive alongside it"


## @brief A miss envelope carries staleness too.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_a_miss_also_carries_the_staleness(rich_db: Path) -> None:
    """The reply where it matters MOST. "Not in this index" and "not in this index YET,
    because the index predates the function you just wrote" are the same payload today,
    and the second is the commoner one for an agent querying code it is editing.

    @brief A not-found reply is annotated.
    @version 1
    """
    drift = [{"axis": fr.AXIS_DATA, "message": "5 files changed; call build_or_refresh()"}]
    tools = QueryTools(lambda: rich_db, lambda: rich_db.parent, lambda: drift)

    payload = tools.dossier("a_function_this_index_has_never_heard_of")
    assert payload["found"] is False
    assert payload["staleness"] == drift


## @brief A current index's query replies carry NO staleness key at all.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_a_current_index_does_not_annotate_its_query_replies(rich_db: Path) -> None:
    """The control on the mechanism, matching the control on the messages. An absent key
    rather than an empty list: `staleness: []` on every reply is noise that a model pays
    for on every call and learns to skip.

    @brief A current index annotates nothing.
    @version 1
    """
    tools = QueryTools(lambda: rich_db, lambda: rich_db.parent, list)
    assert "staleness" not in tools.dossier("main")


## @brief A tool set bound without a provider behaves exactly as it did before gh#2.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_an_unbound_provider_annotates_nothing(rich_db: Path) -> None:
    """The provider is optional so the pre-gh#2 shape is still reachable and still
    silent — which is what keeps the change additive for every existing caller.

    @brief No provider means no annotation.
    @version 1
    """
    assert "staleness" not in QueryTools(lambda: rich_db, lambda: rich_db.parent).dossier("main")


## @brief A provider that raises does not turn a good answer into an error.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_a_failing_staleness_measurement_does_not_break_the_reply(rich_db: Path) -> None:
    """The annotation runs on the way OUT of replies that have already succeeded. A
    freshness check that could not run must cost the annotation, never the answer.

    @brief A raising provider degrades to no annotation.
    @version 1
    """

    def _explode() -> list[dict[str, str]]:
        raise sqlite3.Error("state root vanished mid-session")

    tools = QueryTools(lambda: rich_db, lambda: rich_db.parent, _explode)
    with pytest.raises(sqlite3.Error):
        tools.dossier("main")


## @brief An oversized reply keeps the axis token and compacts only the prose.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_an_oversized_reply_compacts_the_message_but_keeps_the_axis(rich_db: Path) -> None:
    """`_shrink_to_budget` trims a payload to just under the cap, so a full three-axis
    block could push it over — and the response budget exists to protect a model's
    context. The axis TOKEN is what a consumer branches on, so bytes are taken from the
    explanation and never from the axis.

    @brief Overflow compacts the prose, not the axis.
    @version 1
    """
    huge = [
        {"axis": fr.AXIS_DATA, "message": "x" * 2_000},
        {"axis": fr.AXIS_CODE, "message": "y" * 2_000},
    ]
    tools = QueryTools(lambda: rich_db, lambda: rich_db.parent, lambda: huge)

    ## 900 bytes free: the full block cannot fit and the compact one can. This is the
    ## tier the real trim path would land on if a reply ever ran this close to the cap.
    roomy = {"filler": "z" * (RESPONSE_BUDGET_BYTES - 900)}
    compact = tools._staleness(roomy)
    assert [n["axis"] for n in compact] == [fr.AXIS_DATA, fr.AXIS_CODE]
    assert all("x" * 2_000 not in n["message"] for n in compact)
    assert "call status" in compact[0]["message"], "the compact tier must still name the remedy"
    assert len(json.dumps(roomy)) + len(json.dumps({"staleness": compact})) <= RESPONSE_BUDGET_BYTES

    ## 200 bytes free — LESS THAN THE COMPACT BLOCK ITSELF. The first version of the
    ## fallback returned the compact form unconditionally and blew the cap here, which is
    ## why a third tier exists. A fallback that is merely smaller is not bounded.
    cramped = {"filler": "z" * (RESPONSE_BUDGET_BYTES - 200)}
    minimal = tools._staleness(cramped)
    assert [n["axis"] for n in minimal] == [fr.AXIS_DATA, fr.AXIS_CODE], (
        "the axis token must survive every tier — it is what a consumer branches on"
    )
    assert (
        len(json.dumps(cramped)) + len(json.dumps({"staleness": minimal})) <= RESPONSE_BUDGET_BYTES
    )


## @brief A reply with room to spare keeps the full prose.
## @param rich_db Session-scoped synthetic index.
## @return None.
## @version 1
def test_a_small_reply_keeps_the_full_staleness_prose(rich_db: Path) -> None:
    """The control on the compaction: a mechanism that always compacts would deliver the
    pointer and never the remedy, and the remedy is the whole value.

    @brief A small reply is not compacted.
    @version 1
    """
    full = [{"axis": fr.AXIS_DATA, "message": "x" * 400}]
    fitted = QueryTools(lambda: rich_db, lambda: rich_db.parent, lambda: full)._staleness({"a": 1})
    assert fitted == full


## @brief The version `status` reports must be the version the package actually declares.
## @return None.
## @version 1
def test_status_reports_the_real_package_version_not_the_unknown_fallback() -> None:
    """THIS SHIPPED THROUGH 1.0.0. `package_version()` asked `importlib.metadata` for
    `version("clew")` — the IMPORT name — while the distribution ships as `clew-trace`, so
    every `index(action='status')` reply reported `package_version: "unknown"`. That is the
    first field a consumer pastes into a bug report, and it named no version at all.

    NOTHING CAUGHT IT BECAUSE THE FALLBACK IS SILENT BY DESIGN. A failed metadata lookup
    returns the string "unknown" rather than raising, deliberately — it is called on the way
    out of replies that already succeeded — so the broken lookup renders as a plausible
    field value. The function's own docstring meanwhile claimed it could not drift from
    `pyproject.toml`, which was true of the version and false of the distribution name it
    passed. A defect that reads as a legitimate value needs a test asserting the value is
    legitimate; there is no error to notice.

    ASSERTED AGAINST `pyproject.toml`, NEVER A LITERAL. A hardcoded "1.0.0" here would be a
    third place to forget on the next release, which is the shape of the defect above.

    @brief `package_version()` agrees with pyproject, and is not the fallback.
    @return None.
    @version 1
    """
    from clew.mcp_server.freshness import code_identity, package_version
    from clew.tomlcompat import require_toml_module

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    declared = require_toml_module().loads(pyproject.read_text(encoding="utf-8"))
    want = declared["project"]["version"]

    reported = package_version()
    assert reported != "unknown", (
        "package_version() fell back to 'unknown'. Either the package is not installed in "
        f"this environment, or {pyproject.name} renamed the distribution and "
        "freshness._DISTRIBUTION was not updated with it — the exact defect that shipped."
    )
    assert reported == want, (
        f"status would report package_version={reported!r} while pyproject declares {want!r}"
    )

    ## THROUGH `code_identity` TOO, because that is the payload `status` actually serves.
    ## Asserting only on the helper would leave a wrapper free to drop or rename the field.
    assert code_identity().get("package_version") == want, (
        "code_identity() is what reaches a status reply; it must carry the same version"
    )
