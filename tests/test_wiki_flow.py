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
import re
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


# --- W12: animated sequence diagrams --------------------------------------------------------------


## @brief A two-lane flow of three steps, built directly (no index needed).
## @return The Flow.
## @version 1
def _three_steps():
    """@brief Build a flow. @return Flow."""
    from clew.wiki.flow import Flow, Lane, Step

    steps = tuple(
        Step(
            caller="a",
            caller_qualified="a",
            callee=f"f{i}",
            callee_qualified=f"f{i}",
            from_lane="x.py",
            to_lane="y.py" if i % 2 else "x.py",
            file="x.py",
            line=i,
            depth=1,
        )
        for i in range(3)
    )
    lanes = (Lane(id="x.py", label="x.py"), Lane(id="y.py", label="y.py"))
    return Flow(
        entry="a", entry_qualified="a", depth=1, lane_strategy="files", lanes=lanes, steps=steps
    )


def test_an_animated_diagram_plays_the_steps_in_order_with_no_script() -> None:
    """THE ANIMATION IS CSS INSIDE THE SVG: each step is delayed by its position, there is no
    script and nothing remote, reduced motion shows the finished diagram, and the static render is
    unchanged in content.

    @brief `animate=True` staggers steps in call order, script-free.
    @return None.
    """
    import re

    from clew.wiki.svg import STEP_SECONDS, flow_svg

    flow = _three_steps()
    animated = flow_svg(flow, animate=True)
    delays = [float(d) for d in re.findall(r"animation-delay:([\d.]+)s", animated)]
    assert delays == [0.0, STEP_SECONDS, 2 * STEP_SECONDS]
    assert "<script" not in animated and "http" not in animated.replace(
        'xmlns="http://www.w3.org/2000/svg"', ""
    )
    assert "prefers-reduced-motion" in animated
    static = flow_svg(flow)
    assert "animation" not in static
    assert re.findall(r">(f\d)<", static) == re.findall(r">(f\d)<", animated) == ["f0", "f1", "f2"]


def test_a_flow_spec_animates_by_default_and_can_opt_out(tmp_path) -> None:
    """@brief `animate:` in a flow entry is a known key; absent means animated.
    @return None.
    """
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text(
        "wiki:\n  flows:\n    - entry: a\n    - entry: b\n      animate: false\n"
    )
    config, problems = load_wiki_config(tmp_path)
    assert problems == []
    assert [f.animate for f in config.flows] == [True, False]


def test_the_flow_verb_prints_svg(tmp_path, capsys, monkeypatch) -> None:
    """@brief `clew wiki flow ENTRY --svg --animate` prints the animated diagram itself.
    @return None.
    """
    from clew.wiki import command

    monkeypatch.setattr(command, "_flow_object", lambda args, db, repo: _three_steps())
    db = tmp_path / "clew.db"
    db.write_bytes(b"")
    assert command.wiki_main(["flow", "a", "--index", str(db), "--svg", "--animate"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("<svg") and "animation-delay" in out


## @brief A test calling one function five times in a row, then another once.
## @return The Flow.
## @version 1
def _repeated():
    """@brief Build a flow. @return Flow."""
    from clew.wiki.flow import Flow, Lane, Step

    def call(callee: str, line: int) -> Step:
        return Step(
            caller="t",
            caller_qualified="t",
            callee=callee,
            callee_qualified=callee,
            from_lane="t.py",
            to_lane="m.py",
            file="m.py",
            line=line,
            depth=1,
        )

    steps = (*(call("cap", 10 + i) for i in range(5)), call("other", 20))
    lanes = (Lane(id="t.py", label="t.py"), Lane(id="m.py", label="m.py"))
    return Flow(
        entry="t", entry_qualified="t", depth=1, lane_strategy="files", lanes=lanes, steps=steps
    )


def test_repeated_calls_fold_into_one_loop_frame() -> None:
    """OWNER 2026-11-17 (round 5): repeated calls fold into a `loop ×N` frame. Five consecutive
    calls to the same function draw ONE arrow labelled ×5 inside a loop frame; the group still
    names every step it stands for (`data-steps`), so the step table, the step pop-ups and a
    replayed trace keep all five. The animation plays drawn arrows, so a fold leaves no gap.

    @brief Consecutive identical leaf calls draw once, framed `loop ×5`.
    @return None.
    """
    import re

    from clew.wiki.svg import STEP_SECONDS, flow_svg

    animated = flow_svg(_repeated(), animate=True)
    assert re.findall(r'data-step="(\d+)"', animated) == ["0", "5"]
    assert 'data-steps="0 1 2 3 4"' in animated
    assert ">loop ×5<" in animated and ">cap ×5<" in animated
    delays = [float(d) for d in re.findall(r"animation-delay:([\d.]+)s", animated)]
    assert delays == [0.0, STEP_SECONDS]
    assert ">6<" in animated  # the call after the fold keeps its own number


## OWNER 2026-11-17 (round 5): master flows expand what tests RAN. app/main.py lines: 5 load(),
## 7 save(data) inside `if ready`; lib/store.py line 6 parse("x").
_RAN_LOAD_ONLY = {"app/main.py": {4, 5, 6, 8}, "lib/store.py": {1, 2, 5, 6}}


def test_a_measured_flow_expands_what_ran_and_folds_what_did_not(
    indexed: tuple[Path, Path],
) -> None:
    """A CALL THAT RAN EXPANDS past the declared depth (load → parse at depth 1); calls that never
    ran fold into ONE stub per caller (`not_run`), so the diagram shows the exercised path and says
    how much of the static flow no test reached.

    @brief Coverage-guided expansion with a per-caller not-run stub.
    @return None.
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    flow = derive_flow(db, repo, "main", depth=1, executed=_RAN_LOAD_ONLY)
    got = [(s.caller, s.callee, s.not_run) for s in flow.steps]
    assert got == [("main", "load", 0), ("load", "parse", 0), ("main", "", 1)], got
    assert flow.measured is True and flow.capped is False


def test_an_unmeasured_file_is_walked_statically_never_folded_as_not_run(
    indexed: tuple[Path, Path],
) -> None:
    """ABSENCE IS NOT EMPTINESS: lib/store.py is not in the coverage at all, so its calls were not
    MEASURED — never reported as not run. They are emitted as the static flow would.

    @brief A file outside the coverage keeps its static steps.
    @return None.
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    flow = derive_flow(db, repo, "main", depth=1, executed={"app/main.py": {5}})
    got = [(s.caller, s.callee, s.not_run) for s in flow.steps]
    assert got == [("main", "load", 0), ("load", "parse", 0), ("main", "", 1)], got


def test_a_step_cap_stops_the_walk_and_says_so(indexed: tuple[Path, Path]) -> None:
    """@brief `max_steps` bounds a measured flow; `capped` discloses that it did."""
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    flow = derive_flow(db, repo, "main", depth=1, executed=_RAN_LOAD_ONLY, max_steps=1)
    assert len(flow.steps) == 1 and flow.capped is True


def test_a_not_run_stub_is_drawn_as_a_dim_note_not_a_call(indexed: tuple[Path, Path]) -> None:
    """@brief A `not_run` stub reads "… N calls not run", dimmed (class `nr`), never a blank arrow."""
    from clew.wiki.flow import derive_flow
    from clew.wiki.svg import flow_svg

    db, repo = indexed
    svg = flow_svg(derive_flow(db, repo, "main", depth=1, executed=_RAN_LOAD_ONLY))
    assert "… 1 call not run" in svg and 'class="st nr"' in svg


def test_block_lanes_are_the_maps_blocks(indexed: tuple[Path, Path]) -> None:
    """OWNER (round 5): sequence diagrams have BLOCK lanes — the same blocks the map and the
    Architecture tab draw (the build graph's `file_block`), not a path prefix. A file no block
    holds keeps its own path, said rather than dropped.

    @brief P5.6: `blocks` lanes.
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    blocks = {"app/main.py": "Front door", "lib/store.py": "Storage"}
    flow = derive_flow(db, repo, "main", depth=3, lanes="blocks", blocks=blocks)
    assert [lane.id for lane in flow.lanes] == ["Front door", "Storage"]
    assert flow.steps[0].from_lane == "Front door" and flow.steps[0].to_lane == "Storage"
    partial = derive_flow(
        db, repo, "main", depth=3, lanes="blocks", blocks={"app/main.py": "Front door"}
    )
    assert [lane.id for lane in partial.lanes] == ["Front door", "lib/store.py"]


def test_a_flow_names_its_actor(indexed: tuple[Path, Path]) -> None:
    """OWNER (round 5): an ACTOR lane — who starts the flow. Carried on the flow, never a synthetic
    step: slices and replay pair real call sites, and a made-up first call would break both.

    @brief P5.6: the actor.
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    assert (
        derive_flow(db, repo, "main", depth=1, actor="command-line user").actor
        == "command-line user"
    )
    assert derive_flow(db, repo, "main", depth=1).actor == ""


def test_the_default_lane_strategy_is_blocks() -> None:
    """OWNER (round 5) RULING, which replaces the `files` default: a flow spec that names no lane
    strategy gets block lanes.

    @brief P5.6: blocks by default.
    """
    from clew.wiki.config import FlowSpec

    assert FlowSpec(entry="main").lanes == "blocks"


def test_the_actor_lane_is_drawn_first_with_an_arrow_into_the_entry(
    indexed: tuple[Path, Path],
) -> None:
    """@brief P5.6: the actor's head leads the lanes and an `enter` arrow names the entry."""
    from clew.wiki.flow import derive_flow
    from clew.wiki.svg import flow_svg

    db, repo = indexed
    svg = flow_svg(derive_flow(db, repo, "main", depth=1, lanes="files", actor="command-line user"))
    heads = re.findall(r'class="head-t"[^>]*>([^<]+)<', svg)
    assert heads[0] == "command-line user", heads
    assert 'class="enter"' in svg and ">main</text>" in svg
    plain = flow_svg(derive_flow(db, repo, "main", depth=1, lanes="files"))
    assert 'class="enter"' not in plain and "command-line user" not in plain


def test_the_actor_arrow_is_styled_to_be_seen() -> None:
    """FOUND BY LOOKING: the `enter` arrow drew its label and no line, since an SVG line has no
    stroke unless one is given. The diagram's own stylesheet strokes it.

    @brief P5.6: the actor arrow is visible.
    """
    from clew.wiki.svg import _STYLE

    assert ".enter line{stroke:" in _STYLE
