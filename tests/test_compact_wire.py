# SPDX-License-Identifier: MIT
"""The opt-in compact wire shape: neighbour rows grouped by file, shared values stated once.

1.3.7, Track 3 (token cost), parts B and C. Measured on the 1.3.0-final transcripts, `file` was
19% of mattermost's neighbour-row bytes and `confidence`/`edge_class`/`source` repeat the same
value on most rows. The compact shape groups each neighbour list by file and states a reply's
most common value of each repeated field once, in `edge_defaults`.

OPT-IN, because the wire keys are semver-covered and the owner ruled out a major increment
(2026-11-12): the server serves it only when `CLEW_WIRE=compact`, which the clew PLUGIN sets.
Every other MCP consumer keeps today's flat rows.

LOSSLESS, and asserted as such: expanding a compact reply reproduces the flat one exactly.

@brief Tests for the compact neighbour-row wire shape.
@version 1
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from clew.query.payload import compact_neighbours

_FLAT: dict[str, Any] = {
    "subject": "f",
    "callers": [
        {
            "name": "a",
            "source": "ast",
            "confidence": "resolved",
            "edge_class": "call",
            "file": "x.ts",
        },
        {"name": "b", "source": "ast", "confidence": "fuzzy", "edge_class": "call", "file": "y.ts"},
        {
            "name": "c",
            "source": "doxygen_sqlite",
            "confidence": "resolved",
            "edge_class": "call",
            "file": "x.ts",
        },
    ],
    "callees": [
        {
            "name": "d",
            "source": "ast",
            "confidence": "resolved",
            "edge_class": "call",
            "file": "y.ts",
        },
    ],
}


## @brief Undo the compact shape: the oracle the losslessness test compares against.
## @param payload A compact payload.
## @return The flat payload.
## @version 1
def _expand(payload: dict[str, Any]) -> dict[str, Any]:
    """WRITTEN OUT HERE, not imported: comparing the transform with its own inverse would pass
    whatever it does.

    @brief Re-flatten grouped rows and re-apply defaults.
    @return Flat payload.
    """
    out = {k: v for k, v in payload.items() if k != "edge_defaults"}
    defaults = payload.get("edge_defaults", {})
    for key in ("callers", "callees"):
        if key not in payload:
            continue
        rows = []
        for group in payload[key]:
            for row in group["rows"]:
                full = {**row}
                for field, value in defaults.items():
                    full.setdefault(field, value)
                if "file" in group:
                    full["file"] = group["file"]
                rows.append(full)
        out[key] = rows
    return out


## @brief Rows of a flat list in a canonical order, for comparison.
## @param rows Flat rows.
## @return Sorted rows.
## @version 1
def _canon(rows: list[dict[str, Any]]) -> list[str]:
    """@brief Canonicalise. @return Sorted reprs."""
    return sorted(repr(sorted(r.items())) for r in rows)


def test_the_compact_shape_is_lossless() -> None:
    """@brief Expanding a compact reply reproduces the flat rows.
    @return None.
    @version 1
    """
    compact = compact_neighbours(copy.deepcopy(_FLAT))
    expanded = _expand(compact)
    for key in ("callers", "callees"):
        assert _canon(expanded[key]) == _canon(_FLAT[key])


def test_rows_are_grouped_by_file_and_shared_values_stated_once() -> None:
    """@brief Groups by file in first-seen order; the modal values move to edge_defaults.
    @return None.
    @version 1
    """
    compact = compact_neighbours(copy.deepcopy(_FLAT))
    assert [g["file"] for g in compact["callers"]] == ["x.ts", "y.ts"]
    assert compact["edge_defaults"] == {
        "source": "ast",
        "confidence": "resolved",
        "edge_class": "call",
    }
    first = compact["callers"][0]["rows"][0]
    assert first == {"name": "a"}, first
    assert {"name": "c", "source": "doxygen_sqlite"} in compact["callers"][0]["rows"]


def test_a_payload_without_neighbours_is_untouched() -> None:
    """@brief No callers/callees: nothing added, nothing removed.
    @return None.
    @version 1
    """
    payload = {"subject": "v", "sites": [{"file": "a.c", "line": 1}]}
    assert compact_neighbours(copy.deepcopy(payload)) == payload


def test_the_server_serves_compact_only_when_asked(
    rich_db: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE DEFAULT IS UNCHANGED: without `CLEW_WIRE=compact` a dossier's rows are flat.

    @brief CLEW_WIRE=compact switches the dossier reply to the grouped shape.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: rich_db, lambda: repo_root)
    monkeypatch.delenv("CLEW_WIRE", raising=False)
    flat = tools.dossier("sensor_poll")
    assert flat.get("callers") and "file" in flat["callers"][0]
    monkeypatch.setenv("CLEW_WIRE", "compact")
    compact = tools.dossier("sensor_poll")
    assert "rows" in compact["callers"][0] and "edge_defaults" in compact
    assert _canon(_expand(compact)["callers"]) == _canon(flat["callers"])


def test_the_plugin_opts_into_the_compact_shape() -> None:
    """THE PLUGIN IS THE CONSUMER THAT OPTS IN (owner, 2026-11-12): the server it launches is told
    to serve the compact shape; any other MCP consumer is not.

    @brief plugin.json sets CLEW_WIRE=compact for its server.
    @return None.
    @version 1
    """
    import json

    from clew.mcp_server.tools_query import WIRE_COMPACT, WIRE_ENV

    manifest = json.loads(
        (Path(__file__).parent.parent / ".claude-plugin" / "plugin.json").read_text()
    )
    assert manifest["mcpServers"]["clew"]["env"][WIRE_ENV] == WIRE_COMPACT


_DOC = "Fetch the widget by id. Returns the cached widget when present, else loads it."


def test_a_docstring_already_in_the_body_is_served_once() -> None:
    """1.3.9. A Python docstring sits INSIDE the body excerpt, and doxygen serves the same text
    again as `detail` — measured at 14.7% of this repository's dossier bytes. In the compact shape
    `detail` is dropped when the body already carries it, and `detail_in_body: true` says so, so
    an absent `detail` is never read as "undocumented".

    @brief compact_docs drops a detail the body repeats, and marks it.
    @return None.
    @version 1
    """
    from clew.query.payload import compact_docs

    payload = {
        "brief": "Fetch the widget.",
        "detail": _DOC,
        "body": {"lines": ["def fetch(id):", f'    """{_DOC}"""', "    return cache[id]"]},
    }
    out = compact_docs(copy.deepcopy(payload))
    assert "detail" not in out and out["detail_in_body"] is True
    assert out["brief"] == payload["brief"]


def test_a_detail_the_body_does_not_carry_is_kept() -> None:
    """@brief Doc text outside the body (a C comment above it), or no body, keeps `detail`.
    @return None.
    @version 1
    """
    from clew.query.payload import compact_docs

    elsewhere = {"detail": _DOC, "body": {"lines": ["int fetch(int id) {", "  return 0;", "}"]}}
    assert compact_docs(copy.deepcopy(elsewhere)) == elsewhere
    bodiless = {"detail": _DOC}
    assert compact_docs(copy.deepcopy(bodiless)) == bodiless
