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


# --- P4b-2: OpenTelemetry traces imported from any language's run --------------------------------


def _span(sid: str, parent: str, name: str, status: int = 1, events: list | None = None) -> dict:
    return {
        "traceId": "a" * 32,
        "spanId": sid,
        "parentSpanId": parent,
        "name": name,
        "startTimeUnixNano": "1",
        "endTimeUnixNano": "2",
        "attributes": [],
        "events": events or [],
        "status": {"code": status},
    }


def test_an_imported_trace_is_drawn_over_its_test_flow(tmp_path: Path) -> None:
    """ANY LANGUAGE, ONE OVERLAY: an OTLP JSON trace exported by a test run (a C++ test built with
    instrumentation, a JS test with OTel) is matched to the test flow whose test is its root span,
    and the page shows which predicted steps it confirmed, which never ran, what it discovered and
    where it failed. A trace that matches no flow is listed, never dropped.

    @brief Imported OTel traces.
    """
    from clew.cli import _build_argparser, _run_pipeline
    from clew.wiki.build import build_wiki
    from tests.test_wiki_site import (
        _CATALOG,
        _CLI,
        _DATA,
        _FEATURE,
        _JUNIT,
        _OTHER_MAIN,
        _OUT,
        _PYPROJECT,
        _ROADMAP,
        _TEST,
        _WIKI,
    )

    root = tmp_path / "repo"
    for rel, text in {
        "src/__init__.py": "",
        "src/data.py": _DATA,
        "src/out.py": _OUT,
        "src/cli.py": _CLI,
        "tools/other.py": _OTHER_MAIN,
        "pyproject.toml": _PYPROJECT,
        "tests/test_data.py": _TEST,
        "requirements.yaml": _CATALOG,
        "README.md": "# Demo\n",
        "junit.xml": _JUNIT,
        "ROADMAP.md": _ROADMAP,
        "docs/extra.css": ".x{}\n",
        "tests/features/finish.feature": _FEATURE,
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    failure = [
        {
            "name": "exception",
            "attributes": [
                {"key": "code.lineno", "value": {"stringValue": "6"}},
                {"key": "exception.message", "value": {"stringValue": "boom"}},
            ],
        }
    ]
    spans = [
        _span("0000000000000001", "", "test_load", status=2, events=failure),
        _span("0000000000000002", "0000000000000001", "load"),
        _span("0000000000000003", "0000000000000002", "parse"),
        _span("0000000000000004", "0000000000000002", "helper_not_in_flow"),
    ]
    (root / "traces").mkdir()
    (root / "traces" / "run.json").write_text(
        json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]})
    )
    (root / "traces" / "orphan.json").write_text(
        json.dumps(
            {
                "resourceSpans": [
                    {"scopeSpans": [{"spans": [_span("0000000000000009", "", "test_nothing")]}]}
                ]
            }
        )
    )
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(root)]))
    config = tmp_path / "wiki.yaml"
    config.write_text(_WIKI.replace("tests:\n", 'tests:\n  traces: ["traces/*.json"]\n', 1))
    html = build_wiki(root, db, tmp_path / "out", config_path=config)
    page = (html / "flow-test_load-tests-test-data-py.html").read_text()
    panel = page[page.index('class="trace-panel imported"') :].split("</div>")[0]
    assert "traces/run.json" in panel and "confirmed" in panel
    assert "helper_not_in_flow" in panel and "boom" in panel
    assert 'g[data-step="0"]' in page
    flows = (html / "flows.html").read_text()
    assert "traces/orphan.json" in flows and "test_nothing" in flows


def test_installed_code_inside_the_repository_is_never_a_span(tmp_path: Path) -> None:
    """FOUND TRACING CLEW'S OWN TESTS (round 4): clew's `.venv` sits inside the repository, so
    pytest's own `pytest_runtest_call` (site-packages) became the root span and the 20,000-span
    cap filled with pytest internals. A frame in site-packages, or under the running interpreter's
    prefix, is installed code — not the repository's — however its path begins.

    @brief Trace recorder: site-packages and the interpreter prefix are not repository code.
    """
    import sys
    from types import SimpleNamespace

    from clew.wiki._traceplugin import _Recorder

    root = tmp_path / "repo"
    rec = _Recorder(root, root / "tests" / "test_m.py", "test_m")

    def frame(path: str, name: str) -> SimpleNamespace:
        code = SimpleNamespace(co_filename=path, co_name=name, co_firstlineno=1)
        return SimpleNamespace(f_code=code, f_locals={}, f_lineno=1)

    site = str(root / ".venv/lib/python3.10/site-packages/_pytest/python.py")
    assert rec.tracer(frame(site, "pytest_runtest_call"), "call", None) is None
    prefixed = str(Path(sys.prefix) / "lib" / "x.py")
    assert rec.tracer(frame(prefixed, "f"), "call", None) is None
    assert rec.stack == []


def test_only_a_traced_test_gets_a_flow_of_its_own(tmp_path: Path) -> None:
    """FOUND ON CLEW'S OWN WIKI (round 4): three runs were packaged, and the capped set of test
    flows held none of their tests, so every replay landed in "traces whose test has no flow".
    Round 5 (owner 2026-11-17) removed per-test flows and the cap: a test is a slice of the master
    flows, and only a test with a packaged trace keeps a flow, so its replay has a place to land.

    @brief Traced tests keep a flow; no other test has one.
    """
    from unittest import mock

    from clew.wiki import build
    from clew.wiki.testfacts import TestFacts

    facts = {
        "test_a": TestFacts(verifies=[("R", "tag")]),
        "test_z": TestFacts(verifies=[("R", "tag")]),
    }
    keys = {("test_a", "tests/t.py"), ("test_z", "tests/t.py")}
    with mock.patch("clew.wiki.symbols.test_functions", return_value=keys):
        specs = build._test_flows(tmp_path / "x.db", facts, frozenset({"test_z"}))
    ## Round 5 (owner 2026-11-17): only the traced test keeps a flow; test_a is a slice.
    assert {s.entry for s in specs} == {"test_z"}


def test_a_span_records_the_line_it_was_called_from(repo: Path) -> None:
    """2.0.0 (P5.5, traced values): `code.lineno` is the CALLEE's first line, so two calls of one
    function in a test could not be told apart. `clew.call_line` is the caller's line at the call,
    which is what pairs a pinned check with the call it observes. `load([1, 2])` is on line 6.

    @brief Spans carry their call site.
    """
    from clew.wiki.tracerun import spans_of, trace_test

    spans = spans_of(trace_test(repo, "tests/test_m.py::test_load")["otlp"])
    load = next(s for s in spans if s["name"] == "load")
    assert _attrs(load)["clew.call_line"] == "6"


def test_a_real_run_gives_a_pinned_check_its_value(repo: Path) -> None:
    """END TO END (2.0.0, P5.5): the plugin's `clew.call_line` and the pins' lines agree. In
    `test_load`, `got = load([1, 2])` (line 6) binds `got`, and `assert got == [2, 4]` reads it,
    so the check observes `load` via `got` and its traced value is `[2, 4]`.

    @brief A recorded run's value reaches the pinned check.
    """
    from clew.wiki.checkpins import pin_checks, traced_values
    from clew.wiki.tracerun import trace_test

    run = trace_test(repo, "tests/test_m.py::test_load")
    body = (repo / "tests" / "test_m.py").read_text().splitlines()[3:7]
    pins = pin_checks(body, "tests/test_m.py", {"load"}, first_line=4)
    assert [(p.kind, p.variable, p.bound_line) for p in pins] == [("via variable", "got", 6)]
    assert traced_values(pins, run["otlp"], "test_load") == {0: "[2, 4]"}


def _valued(sid: str, parent: str, name: str, args: str, ret: str) -> dict:
    """@brief A span carrying the values a run recorded. @return Span."""
    return {
        "spanId": sid,
        "parentSpanId": parent,
        "name": name,
        "attributes": [
            {"key": "clew.args", "value": {"stringValue": args}},
            {"key": "clew.return", "value": {"stringValue": ret}},
        ],
        "events": [],
        "status": {"code": 1},
    }


def test_the_overlay_gives_each_confirmed_step_its_values() -> None:
    """OWNER (round 5, P5.6): replay WITH VALUES. Each predicted step the run confirmed carries
    what it was called with and returned. A pair called twice pairs IN ORDER — the second
    predicted `load → parse` is the second observed one; a step the run never made has none.

    @brief Replay values per step.
    """
    from clew.wiki.tracerun import overlay

    otlp = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            _valued("t", "", "test_load", "", "None"),
                            _valued("a", "t", "load", "items=[1, 2]", "[2, 4]"),
                            _valued("b", "a", "parse", "raw=1", "2"),
                            _valued("c", "a", "parse", "raw=2", "4"),
                        ]
                    }
                ]
            }
        ]
    }
    expected = [("test_load", "load"), ("load", "parse"), ("load", "parse"), ("load", "finish")]
    values = overlay(expected, otlp)["values"]
    assert values[1] == {"args": "raw=1", "return": "2"} and values[2] == {
        "args": "raw=2",
        "return": "4",
    }
    assert values[0] == {"args": "items=[1, 2]", "return": "[2, 4]"} and values[3] is None


def test_a_steps_dialog_carries_its_recorded_values() -> None:
    """@brief P5.6: the step data gains `called_with` / `returned` from the run, unless withheld."""
    from clew.wiki.config import Audience
    from clew.wiki.flowpage import _SCRIPT, with_values

    data = [{"caller": "test_load", "callee": "load"}, {"caller": "load", "callee": "parse"}]
    otlp = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            _valued("t", "", "test_load", "", "None"),
                            _valued("a", "t", "load", "items=[1]", "[2]"),
                        ]
                    }
                ]
            }
        ]
    }
    out = with_values(data, otlp, Audience())
    assert out[0]["called_with"] == "items=[1]" and out[0]["returned"] == "[2]"
    assert "called_with" not in out[1], "a step the run never made carries no values"
    hidden = with_values(data, otlp, Audience(exclude_bodies=True))
    assert all("called_with" not in r for r in hidden), "values are withheld with the bodies"
    assert "s.called_with" in _SCRIPT and "s.returned" in _SCRIPT


def test_a_master_flow_takes_the_subtree_a_test_trace_reaches() -> None:
    """X-2 (owner review 2, 2026-11-22): "I don't see the dossier being built"; owner Q/A: real values,
    traced. A traced test's root span is the TEST, so its trace could light only the test's own flow,
    never the `dossier` master flow it calls. A flow with no trace rooted at its entry takes the
    subtree under the first span named after its entry, from any trace.

    @brief A flow's trace: rooted at its entry, else the subtree under it.
    """
    from clew.wiki.tracerun import root_name, spans_of, trace_for

    def span(i, name, parent, start):
        return {"spanId": i, "parentSpanId": parent, "name": name, "startTimeUnixNano": start}

    otlp = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            span("1", "test_dossier_caps", "", 1),
                            span("2", "dossier", "1", 2),
                            span("3", "_answered", "2", 3),
                            span("4", "other", "1", 9),
                        ]
                    }
                ]
            }
        ]
    }
    traces = {root_name(otlp): ("build/traces/t.json", otlp)}
    rel, sub = trace_for("dossier", traces)
    assert rel == "build/traces/t.json" and root_name(sub) == "dossier"
    assert sorted(s["name"] for s in spans_of(sub)) == ["_answered", "dossier"]
    assert trace_for("test_dossier_caps", traces) == traces["test_dossier_caps"]
    assert trace_for("absent", traces) is None
