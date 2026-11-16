# SPDX-License-Identifier: MIT
"""A traced test run, overlaid on the expected flow (round 3, P4b-1).

Owner 2026-11-15: "when executing a test in wiki, I expect it to be VISUAL, overlaid on top of
EXPECTED flow, showing how the test catches failures". A test is run IN A SUBPROCESS (it
executes the repository's code, so it is always an explicit act) under a pytest plugin that
records every call between functions of the repository's own files, with the values passed and
returned, as OpenTelemetry spans (OTLP JSON); the test function's own executed lines mark its
assertion checkpoints, and a failing assertion marks the failure point.

The OVERLAY compares the run with the flow the index derived for the same test: a step both
predicted and observed is CONFIRMED, a predicted step that did not run is NOT EXECUTED, an
observed call the index did not predict is DISCOVERED (index-quality feedback).

@brief Tests for traced test runs and their overlay on the expected flow.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SRC = '''\
def load(items):
    """Load."""
    out = [parse(i) for i in items]
    if not out:
        finish()
    return out


def parse(raw):
    """Parse."""
    return raw * 2


def finish():
    """Finish."""
    return None
'''

_TEST = '''\
from src.m import load


def test_load():
    """Covers load."""
    got = load([1, 2])
    assert got == [2, 4]


def test_broken():
    """Fails on purpose."""
    got = load([3])
    assert got == [7], "parse doubled it"
'''


## @brief A tiny repository with one module and two tests.
## @param tmp_path Scratch.
## @return The repository root.
## @version 1
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """@brief Build the fixture. @return Root."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "m.py").write_text(_SRC)
    (root / "tests" / "test_m.py").write_text(_TEST)
    return root


def _attrs(span: dict) -> dict[str, str]:
    return {a["key"]: next(iter(a["value"].values())) for a in span.get("attributes", [])}


def test_a_run_is_recorded_as_spans_between_repository_functions(repo: Path) -> None:
    """@brief Spans: one per call between repo functions, nested as called, with values."""
    from clew.wiki.tracerun import spans_of, trace_test

    run = trace_test(repo, "tests/test_m.py::test_load")
    assert run["passed"] is True
    spans = spans_of(run["otlp"])
    by_name = {s["name"]: s for s in spans}
    assert {"test_load", "load", "parse"} <= set(by_name) and "finish" not in by_name
    assert by_name["load"]["parentSpanId"] == by_name["test_load"]["spanId"]
    assert by_name["parse"]["parentSpanId"] == by_name["load"]["spanId"]
    attrs = _attrs(by_name["load"])
    assert attrs["code.filepath"] == "src/m.py" and attrs["code.function"] == "load"
    assert attrs["clew.args"] == "items=[1, 2]" and attrs["clew.return"] == "[2, 4]"
    assert sum(1 for s in spans if s["name"] == "parse") == 2


def test_a_failing_assertion_is_the_failure_point(repo: Path) -> None:
    """@brief The test span is an error, carrying the assertion's line and message."""
    from clew.wiki.tracerun import spans_of, trace_test

    run = trace_test(repo, "tests/test_m.py::test_broken")
    assert run["passed"] is False
    test_span = next(s for s in spans_of(run["otlp"]) if s["name"] == "test_broken")
    assert test_span["status"]["code"] == 2
    event = next(e for e in test_span["events"] if e["name"] == "exception")
    detail = _attrs(event)
    assert detail["code.lineno"] == "13" and "parse doubled it" in detail["exception.message"]
    assert run["checkpoints"] == [
        {"line": 13, "text": 'assert got == [7], "parse doubled it"', "outcome": "failed"}
    ]


def test_passing_assertions_are_checkpoints(repo: Path) -> None:
    """@brief Each assertion the test executed is a checkpoint with its outcome."""
    from clew.wiki.tracerun import trace_test

    run = trace_test(repo, "tests/test_m.py::test_load")
    assert run["checkpoints"] == [{"line": 7, "text": "assert got == [2, 4]", "outcome": "passed"}]


def test_the_overlay_confirms_misses_and_discovers(repo: Path) -> None:
    """THE EXPECTED FLOW IS THE INDEX'S: `load` might call `finish`, which this run never did
    (not executed); a call the run made that the flow does not predict is discovered.

    @brief Overlay.
    """
    from clew.wiki.tracerun import overlay, trace_test

    run = trace_test(repo, "tests/test_m.py::test_load")
    expected = [("test_load", "load"), ("load", "parse"), ("load", "finish"), ("load", "len")]
    result = overlay(expected, run["otlp"])
    assert result["steps"] == ["confirmed", "confirmed", "not executed", "not executed"]
    assert result["discovered"] == []
    partial = overlay([("test_load", "load")], run["otlp"])
    assert partial["discovered"] == [["load", "parse"]]


def test_the_cli_writes_otlp_json_and_the_overlay(repo: Path, tmp_path: Path) -> None:
    """@brief `clew wiki trace-run` writes the spans (OTLP JSON) and prints the overlay."""
    from clew.wiki.command import wiki_main

    out = tmp_path / "spans.json"
    assert (
        wiki_main(
            [
                "trace-run",
                "--repo-root",
                str(repo),
                "--test",
                "tests/test_m.py::test_load",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    doc = json.loads(out.read_text())
    scope = doc["resourceSpans"][0]["scopeSpans"][0]
    assert scope["scope"]["name"] == "clew.wiki.trace" and scope["spans"]
    assert len(scope["spans"][0]["traceId"]) == 32 and len(scope["spans"][0]["spanId"]) == 16


# --- from the hub and the page -------------------------------------------------------------------


def test_the_hub_runs_a_test_only_when_running_is_switched_on(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RUNNING A TEST EXECUTES THE REPOSITORY'S CODE: the hub refuses unless `CLEW_WIKI_RUN=1`,
    and says how to switch it on; switched on, it answers with the run and its overlay.

    @brief Hub trace endpoint.
    """
    import urllib.error
    import urllib.request

    from clew.cli import _build_argparser, _run_pipeline
    from clew.mcp_server.state import TargetRegistry
    from clew.mcp_server.wikihub import WikiHub

    home = tmp_path / "state"
    target = TargetRegistry(home).register(repo)
    _run_pipeline(
        _build_argparser().parse_args(["--output", target.db_path, "--repo-root", str(repo)])
    )
    hub = WikiHub(home, builder=lambda t, out: out)
    hub.start()
    url = f"http://127.0.0.1:{hub.port}/api/{target.slug}/trace?test=tests/test_m.py::test_load"
    request = urllib.request.Request(url, headers={"Cookie": f"clew_wiki={hub.token}"})
    try:
        monkeypatch.delenv("CLEW_WIKI_RUN", raising=False)
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=30)
        assert refused.value.code == 403 and "CLEW_WIKI_RUN" in refused.value.read().decode()
        monkeypatch.setenv("CLEW_WIKI_RUN", "1")
        with urllib.request.urlopen(request, timeout=120) as reply:
            run = json.loads(reply.read())
        assert run["passed"] is True and run["overlay"]["steps"]
        assert set(run["overlay"]["steps"]) <= {"confirmed", "not executed"}
        assert "confirmed" in run["overlay"]["steps"]
    finally:
        hub.stop()


def test_a_test_flow_page_names_its_test_and_the_live_script_can_run_it() -> None:
    """@brief A test flow's block carries its node id; the live script offers the traced run."""
    from clew.mcp_server.wikihub import _LIVE_JS
    from clew.wiki.config import FlowSpec
    from clew.wiki.flowpage import test_node

    assert (
        test_node(FlowSpec(entry="test_load", file="tests/test_m.py", role="tests"))
        == "tests/test_m.py::test_load"
    )
    assert test_node(FlowSpec(entry="load", file="src/m.py", role="product")) == ""
    assert (
        "data-test-node" in _LIVE_JS and "obs-confirmed" in _LIVE_JS and "/trace?test=" in _LIVE_JS
    )


def test_a_run_uses_the_repositorys_own_interpreter(tmp_path: Path) -> None:
    """THE TEST RUNS WHERE ITS DEPENDENCIES ARE: the repository's own virtual environment when it
    has one (`.venv`, then `venv`), clew's interpreter otherwise. The tracer is handed to that
    interpreter as a standalone plugin file — the target environment needs pytest, not clew.

    @brief Interpreter choice.
    """
    import sys

    from clew.wiki.tracerun import interpreter_for

    plain = tmp_path / "plain"
    plain.mkdir()
    assert interpreter_for(plain) == Path(sys.executable)
    own = tmp_path / "own"
    (own / "venv" / "bin").mkdir(parents=True)
    (own / "venv" / "bin" / "python").symlink_to(sys.executable)
    assert interpreter_for(own) == own / "venv" / "bin" / "python"
    (own / ".venv" / "bin").mkdir(parents=True)
    (own / ".venv" / "bin" / "python").symlink_to(sys.executable)
    assert interpreter_for(own) == own / ".venv" / "bin" / "python"
