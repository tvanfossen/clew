# SPDX-License-Identifier: MIT
"""`clew wiki flow`: a sequence diagram derived from the index, not authored.

1.4.0 Track 4, W3 (#67, the fourth consumer's ask: "diagrams should be FORMED from the index").
From an entry function the flow walks the IDENTITY-scoped call graph (W1) in each caller's own
call order (W2), emitting one step per call with the frames around it, and assigns each function
to a lane (its file, its top-level package, or its thread). Every step is an index edge, so there
is no "unresolved step" to report — the ratchet the authored-diagram design needed is not needed.

@brief Tests for clew.wiki.flow.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_APP = """\
from store import load, save


def main(ready):
    data = load()
    if ready:
        save(data)
    return data
"""

_STORE = """\
def parse(raw):
    return raw


def load():
    return parse("x")


def save(data):
    return data
"""


## @brief A two-file Python repository and its index.
## @param tmp_path Scratch directory.
## @return (index path, repo root).
## @version 1
@pytest.fixture()
def indexed(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Build the fixture index. @return Paths."""
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "lib").mkdir()
    (repo / "app" / "main.py").write_text(_APP)
    (repo / "lib" / "store.py").write_text(_STORE)
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out, repo


def test_a_flow_follows_the_calls_in_order_with_frames(indexed: tuple[Path, Path]) -> None:
    """@brief main → load → parse, then main → save inside `if`, lanes by package.
    @return None.
    @version 1
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    flow = derive_flow(db, repo, "main", depth=3, lanes="packages")
    steps = [(s.caller, s.callee, [f.kind for f in s.frames]) for s in flow.steps]
    assert steps == [
        ("main", "load", []),
        ("load", "parse", []),
        ("main", "save", ["if"]),
    ], steps
    assert [lane.id for lane in flow.lanes] == ["app", "lib"]
    assert flow.steps[0].from_lane == "app" and flow.steps[0].to_lane == "lib"


def test_depth_bounds_the_walk_and_stop_at_ends_a_branch(indexed: tuple[Path, Path]) -> None:
    """@brief depth=1 shows only the entry's own calls; stop_at keeps a callee but not its calls.
    @return None.
    @version 1
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    shallow = derive_flow(db, repo, "main", depth=1, lanes="files")
    assert [s.callee for s in shallow.steps] == ["load", "save"]
    stopped = derive_flow(db, repo, "main", depth=3, lanes="files", stop_at=("load",))
    assert [s.callee for s in stopped.steps] == ["load", "save"]


def test_an_unknown_entry_is_refused_by_name(indexed: tuple[Path, Path]) -> None:
    """@brief No flow is invented for an entry the index does not hold.
    @return None.
    @version 1
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    with pytest.raises(ValueError, match="no_such_entry"):
        derive_flow(db, repo, "no_such_entry")


def test_the_cli_prints_the_flow_as_json(
    indexed: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief `clew wiki flow ENTRY --index DB --repo-root DIR` prints flow JSON with a version.
    @return None.
    @version 1
    """
    from clew.wiki.command import wiki_main

    db, repo = indexed
    code = wiki_main(
        ["flow", "main", "--index", str(db), "--repo-root", str(repo), "--lanes", "files"]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and data["flow_version"] == 1 and data["entry"] == "main"
    assert [s["callee"] for s in data["steps"]][:2] == ["load", "parse"]
