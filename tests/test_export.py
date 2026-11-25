# SPDX-License-Identifier: MIT
"""The stable export API answers exactly what the MCP surface answers, minus the MCP boundary.

1.3.1, Track 1 (export API). A non-MCP consumer — a C++ host, the planned `clew wiki` generator
(#67 point 1: "today the pilot imports clew query/wire internals") — needs the dossier and search
replies WITHOUT reaching into `clew.mcp_server`. The contract pinned here is PARITY: for every
subject and every corpus, `clew.query.export_*` returns the MCP reply with only the MCP-boundary
parts removed — the byte budget, the neighbour cap, and the `target`/`staleness`/sub-index stamps
that describe the server rather than the answer. Everything else (the notes, the ambiguity block,
gate definitions, absent-key elision) is answer content and must be identical.

A parity test that compared a hand-picked subject or two would pass on the subjects that happen
not to exercise a helper; this one walks every distinct name the fixture indexes.

@brief Parity tests for clew.query's export API.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from clew import query as q
from clew.mcp_server import tools_query
from clew.mcp_server.tools_query import CORPORA, QueryTools

## Keys the MCP boundary stamps onto a reply. They describe the SERVER (which repository it routed
## to, whether its index is stale, which sub-index answered) rather than the answer, so an export
## consumer — which names its database explicitly — does not get them.
_BOUNDARY_KEYS = ("target", "staleness", "sub_index", "not_searched")


## @brief A tool set bound to the session index and its working tree, with the budget out of reach.
## @param rich_db The synthetic index.
## @param repo_root The C source tree it indexes.
## @param monkeypatch Pytest monkeypatch.
## @return The bound tool set.
## @version 1
@pytest.fixture()
def unbudgeted(rich_db: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> QueryTools:
    """THE BUDGET IS THE ONE LOSSY THING AT THE BOUNDARY, so parity is asserted with it lifted:
    the export has no context window to protect and must return every row.

    @brief Bind QueryTools with an unreachable byte budget.
    @return QueryTools over rich_db.
    @version 1
    """
    monkeypatch.setattr(tools_query, "RESPONSE_BUDGET_BYTES", 10**9)
    return QueryTools(lambda: rich_db, lambda: repo_root)


## @brief Strip the MCP-boundary stamps from a reply.
## @param reply An MCP tool reply.
## @return The reply without boundary keys, recursively for batch entries.
## @version 1
def _answer_only(reply: dict[str, Any]) -> dict[str, Any]:
    """@brief Remove boundary keys. @return The answer part."""
    out = {k: v for k, v in reply.items() if k not in _BOUNDARY_KEYS}
    if isinstance(out.get("results"), list):
        out["results"] = [
            {k: v for k, v in e.items() if k not in _BOUNDARY_KEYS} if isinstance(e, dict) else e
            for e in out["results"]
        ]
    return out


## @brief Strip the export's own version stamp.
## @param payload An export payload.
## @return The payload without `wire_version`.
## @version 1
def _without_version(payload: dict[str, Any]) -> dict[str, Any]:
    """@brief Remove wire_version. @return The payload."""
    assert payload.get("wire_version") == q.WIRE_VERSION, "every export payload carries the version"
    return {k: v for k, v in payload.items() if k != "wire_version"}


## @brief Every distinct indexed name in the fixture, plus one that is not indexed.
## @param db The fixture index.
## @return Sorted names.
## @version 1
def _subjects(db: Path) -> list[str]:
    """@brief Distinct memberdef/compounddef names. @return Names."""
    with sqlite3.connect(db) as conn:
        names = {r[0] for r in conn.execute("SELECT DISTINCT name FROM memberdef") if r[0]}
        names |= {r[0] for r in conn.execute("SELECT DISTINCT name FROM compounddef") if r[0]}
    return sorted(names) + ["definitely_not_indexed_xyz"]


def test_the_export_api_is_public() -> None:
    """THE SURFACE IS THE PROMISE. semver covers what `clew.query` re-exports, so the export
    must be reachable from there — a function a consumer has to import from a submodule is an
    internal by this repository's own definition.

    @brief export_dossier, export_search and WIRE_VERSION are in clew.query.__all__.
    @return None.
    @version 1
    """
    for name in ("export_dossier", "export_search", "WIRE_VERSION", "EXPORT_CORPORA"):
        assert name in q.__all__, name
    assert set(q.EXPORT_CORPORA) == set(CORPORA)


def test_every_subject_exports_what_the_mcp_dossier_answers(
    rich_db: Path, repo_root: Path, unbudgeted: QueryTools
) -> None:
    """PARITY OVER EVERY NAME, not a sample. The neighbour cap is lifted on the MCP side by asking
    for more neighbours than any fixture symbol has; the export applies none.

    @brief export_dossier == MCP dossier minus boundary stamps, for every indexed name.
    @return None.
    @version 1
    """
    for name in _subjects(rich_db):
        mcp = _answer_only(unbudgeted.dossier(name, max_neighbors=10**6))
        exported = _without_version(
            q.export_dossier(rich_db, name, repo_root=repo_root, max_neighbors=10**6)
        )
        if mcp.get("found") is False:
            _assert_same_miss(exported, mcp, name)
            continue
        assert exported == mcp, name


## @brief A single-subject miss agrees with the MCP miss in everything but its routing advice.
## @param exported The export miss.
## @param mcp The MCP miss, boundary stamps removed.
## @param name The subject.
## @return None.
## @version 1
def _assert_same_miss(exported: dict[str, Any], mcp: dict[str, Any], name: str) -> None:
    """THE ROUTING SENTENCE IS BOUNDARY, THE REST IS ANSWER. The MCP miss tells a model to check
    `target` and call status — advice about a SERVER, which an export caller does not have. The
    kind-limitation clause and the recovery hint are about the INDEX and must be identical, so
    the export note's tail after its first two sentences must end the MCP note verbatim.

    @brief Compare two misses modulo the routing advice.
    @return None.
    """
    assert {k: v for k, v in exported.items() if k != "note"} == {
        k: v for k, v in mcp.items() if k != "note"
    }, name
    tail = exported["note"].split("malformed call.", 1)[1]
    assert mcp["note"].endswith(tail), name
    assert "target" not in exported["note"], f"{name}: routing advice leaked into the export"


def test_a_batch_exports_what_the_mcp_batch_answers(
    rich_db: Path, repo_root: Path, unbudgeted: QueryTools
) -> None:
    """@brief A list subject exports the same batch envelope, entries positional.
    @return None.
    @version 1
    """
    names = _subjects(rich_db)[: q.MAX_BATCH_SYMBOLS - 1] + ["definitely_not_indexed_xyz"]
    mcp = _answer_only(unbudgeted.dossier(names))
    exported = _without_version(q.export_dossier(rich_db, names, repo_root=repo_root))
    assert exported == mcp


@pytest.mark.parametrize("corpus", sorted(CORPORA))
@pytest.mark.parametrize("text", ["", "mutex", "dm", "no_such_token_xyz"])
def test_every_corpus_exports_what_the_mcp_search_answers(
    rich_db: Path, repo_root: Path, unbudgeted: QueryTools, corpus: str, text: str
) -> None:
    """@brief export_search == MCP search minus boundary stamps, for every corpus.
    @return None.
    @version 1
    """
    mcp = _answer_only(unbudgeted.search(text, corpus=corpus))
    exported = _without_version(q.export_search(rich_db, text, corpus=corpus, repo_root=repo_root))
    assert exported == mcp


def test_an_unknown_corpus_is_refused_by_name(rich_db: Path) -> None:
    """@brief An unknown corpus raises, naming the known ones.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="symbols"):
        q.export_search(rich_db, "x", corpus="nope")


def test_the_committed_wire_manifest_is_current() -> None:
    """A COVERED KEY CANNOT CHANGE UNNOTICED. The manifest is regenerated from the reply
    dataclasses and compared with `docs/wire-keys.json`; a renamed or removed field fails here
    and must be shipped with a `WIRE_VERSION` decision (an added one is additive — regenerate).

    @brief docs/wire-keys.json equals the generated manifest.
    @return None.
    @version 1
    """
    import json

    from clew.query.wire_manifest import wire_manifest

    committed = json.loads((Path(__file__).parent.parent / "docs" / "wire-keys.json").read_text())
    assert committed == wire_manifest(), (
        "the wire keys changed — regenerate with "
        "`.venv/bin/python -m clew.query.wire_manifest > docs/wire-keys.json` and decide whether "
        "WIRE_VERSION moves (a removed or renamed key moves it)"
    )


def test_the_flow_json_shape_is_in_the_manifest() -> None:
    """PS1 (owner Q/A 2026-11-19): `clew wiki flow` JSON is covered, recorded after P5's sequence
    changes (block lanes, the actor, loop folding, replay values) so 2.0.0 ships its final shape.
    A later change is additive or bumps `flow_version`.

    @brief The Flow types are in docs/wire-keys.json.
    """
    from clew.query.wire_manifest import wire_manifest
    from clew.wiki.flow import FLOW_VERSION

    flow = wire_manifest()["flow"]
    assert flow["flow_version"] == FLOW_VERSION
    assert {"Flow", "Lane", "Step"} <= set(flow["types"])
    assert "actor" in flow["types"]["Flow"] and "lanes" in flow["types"]["Flow"]


def test_the_impact_report_shape_is_in_the_manifest() -> None:
    """PS3 (owner Q/A 2026-11-19): `impact.json` carries a `schema_version`, and its keys are
    covered like the wire keys.

    @brief impact.json's shape is in docs/wire-keys.json.
    """
    from clew.guard.impact import IMPACT_SCHEMA_VERSION
    from clew.query.wire_manifest import wire_manifest

    impact = wire_manifest()["impact"]
    assert impact["schema_version"] == IMPACT_SCHEMA_VERSION
    ## SPEC CHANGED (2.1, clew#74, owner 2026-11-25): `tests` on an entry, `via` on a function,
    ## and the report's own `unmapped` / `unmapped_files` — additive, so schema_version stays 1.
    assert impact["entry_keys"] == ["functions", "req_id", "req_name", "reviewers", "tests"]
    assert impact["function_keys"] == ["file", "name", "version", "via"]
    assert impact["report_keys"] == ["entries", "schema_version", "unmapped", "unmapped_files"]
