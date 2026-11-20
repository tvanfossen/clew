# SPDX-License-Identifier: MIT
"""A traced test run and its overlay on the expected flow (round 3, P4b).

Owner 2026-11-15: "when executing a test in wiki, I expect it to be VISUAL, overlaid on top of
EXPECTED flow, showing how the test catches failures". A test is run in a SUBPROCESS under
`_traceplugin` — running a test executes the repository's code, so it is always an explicit act
(`clew wiki trace-run`, or the hub with `CLEW_WIKI_RUN=1`) and never part of a build.

The run comes back as OpenTelemetry spans in OTLP JSON — one span per call between functions of
the repository's own files, nested as called, carrying the values passed and returned — plus the
test's ASSERTION CHECKPOINTS (each assertion it executed, passed or failed) and, when it failed,
the FAILURE POINT: the assertion's line and message, an `exception` event on the test's span.

`overlay` compares the run with the flow the index predicted for the same test: each predicted
step CONFIRMED (observed) or NOT EXECUTED; observed calls the flow did not predict are DISCOVERED.

@brief Run a test under a tracer, import other runs' traces, overlay them on the expected flow.
@version 2
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .._common import logger

## The tracer's module name in the run's interpreter: neutral, so it cannot shadow anything.
_PLUGIN_FILE = "clew_trace_plugin.py"
## Where a repository's own virtual environment's interpreter is looked for, in order.
_VENVS = (
    ".venv/bin/python",
    "venv/bin/python",
    ".venv/Scripts/python.exe",
    "venv/Scripts/python.exe",
)


## @brief Run one test under the tracer, in a subprocess.
## @param repo_root The repository (the run's working directory and the traced tree).
## @param nodeid The pytest node id, e.g. `tests/test_m.py::test_load`.
## @return {passed, otlp, checkpoints, failure, dropped}.
## v2: the repository's own interpreter; the plugin as a standalone file (the packaging gate
## found the first cut importing pytest into clew and running with clew's interpreter).
## v3: interpreter and timeout from the repository's wiki: section (2.0.0, R5-CFG C5/W6)
## @version 3
## @req REQ-DDB-WIKI-035
def trace_test(repo_root: Path, nodeid: str) -> dict[str, Any]:
    """THE REPOSITORY'S OWN PYTEST CONFIG STILL APPLIES, except what would hide the run: a
    parallel runner is disabled (the tracer follows one thread of one process). THE TEST RUNS IN
    THE REPOSITORY'S OWN INTERPRETER (`interpreter_for`) — its dependencies live there, not in
    clew's — and the tracer reaches it as a standalone plugin file on `PYTHONPATH`, so that
    environment needs pytest and never clew.

    @brief Trace a test.
    @return The run.
    """
    root = Path(repo_root).resolve()
    ## R5-CFG C5/W6 (2.0.0): the repository states its interpreter and timeout (`wiki.trace_python`,
    ## `wiki.trace_timeout`); an invalid section falls back to the defaults, said by `wiki check`.
    from .config import load_wiki_config

    config, _problems = load_wiki_config(root)
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "run.json"
        shutil.copyfile(Path(__file__).with_name("_traceplugin.py"), Path(scratch) / _PLUGIN_FILE)
        path = os.pathsep.join(p for p in (scratch, os.environ.get("PYTHONPATH", "")) if p)
        env = {
            **os.environ,
            "CLEW_TRACE_ROOT": str(root),
            "CLEW_TRACE_OUT": str(out),
            "PYTHONPATH": path,
        }
        argv = [
            str(interpreter_for(root, config.trace_python)),
            "-m",
            "pytest",
            nodeid,
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
            "-p",
            _PLUGIN_FILE.removesuffix(".py"),
        ]
        done = subprocess.run(
            argv,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=config.trace_timeout,
            check=False,
        )
        if not out.is_file():
            raise RuntimeError(
                f"the traced run wrote nothing: {(done.stderr or done.stdout)[-2000:]}"
            )
        raw = json.loads(out.read_text(encoding="utf-8"))
    if "error" in raw:
        raise RuntimeError(f"{raw['error']} for {nodeid!r}: {(done.stdout or done.stderr)[-2000:]}")
    test_file = root / nodeid.split("::", 1)[0]
    return {
        "passed": raw["exitstatus"] == 0,
        "otlp": _otlp(raw["spans"], nodeid),
        "checkpoints": _checkpoints(test_file, raw["lines"], raw["failure"]),
        "failure": raw["failure"],
        "dropped": raw["dropped"],
    }


## @brief The interpreter a repository's tests run under.
## @param repo_root The repository.
## @param declared `wiki.trace_python`, repo-relative, or None.
## @return The declared interpreter, else its own virtual environment's, else clew's.
## v2 (2.0.0): a declared interpreter, and the fallback is said (R5-CFG W6).
## @version 2
## @req REQ-DDB-WIKI-035
def interpreter_for(repo_root: Path, declared: str | None = None) -> Path:
    """A DECLARED interpreter (`wiki.trace_python`) wins; else a conventional venv under the root;
    else clew's own interpreter — SAID AT WARNING (R5-CFG W6, 2.0.0), because the target's packages
    are usually not there and the run then fails with an ImportError that reads as a test failure.

    @brief Interpreter.
    @return Path.
    """
    if declared:
        return Path(repo_root) / declared
    for rel in _VENVS:
        candidate = Path(repo_root) / rel
        if candidate.exists():
            return candidate
    logger.warning(
        "trace-run: no interpreter declared (`wiki.trace_python`) and no %s under %s — running "
        "the test under clew's own interpreter %s, which may lack the repository's packages",
        " / ".join(_VENVS),
        repo_root,
        sys.executable,
    )
    return Path(sys.executable)


## @brief The spans as an OTLP JSON document.
## @param spans The spans.
## @param nodeid The test.
## @return The document.
## @version 1
## @utility
def _otlp(spans: list[dict[str, Any]], nodeid: str) -> dict[str, Any]:
    """@brief OTLP. @return Document."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "clew wiki trace-run"}},
                        {"key": "test.nodeid", "value": {"stringValue": nodeid}},
                    ]
                },
                "scopeSpans": [{"scope": {"name": "clew.wiki.trace"}, "spans": spans}],
            }
        ]
    }


## @brief Every span of an OTLP JSON document.
## @param otlp The document.
## @return Spans, in recorded order.
## @version 1
## @req REQ-DDB-WIKI-035
def spans_of(otlp: dict[str, Any]) -> list[dict[str, Any]]:
    """@brief Spans. @return List."""
    return [
        span
        for resource in otlp.get("resourceSpans") or []
        for scope in resource.get("scopeSpans") or []
        for span in scope.get("spans") or []
    ]


## @brief The assertions the test executed, each passed or failed.
## @param test_file The test's file.
## @param lines The test function's executed lines.
## @param failure The failure point, or None.
## @return Checkpoints in executed order: {line, text, outcome}.
## @version 1
## @utility
def _checkpoints(test_file: Path, lines: list[int], failure: dict | None) -> list[dict[str, Any]]:
    """@brief Checkpoints. @return List."""
    from .testfacts import assertions

    try:
        source = test_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in dict.fromkeys(lines):
        found = assertions(source[line - 1 : line + 7]) if 0 < line <= len(source) else []
        if found and source[line - 1].strip().startswith(found[0].split("(")[0].split(" ")[0]):
            failed = bool(failure) and failure.get("line") == line
            out.append(
                {"line": line, "text": found[0], "outcome": "failed" if failed else "passed"}
            )
    return out


## @brief Compare a run with the expected flow.
## @param expected (caller, callee) per expected step, in flow order.
## @param otlp The run's spans.
## @return {steps: [confirmed | not executed], discovered: [[caller, callee]]}.
## v2: replay with values (2.0.0, P5.6)
## @version 2
## @req REQ-DDB-WIKI-035
def overlay(expected: list[tuple[str, str]], otlp: dict[str, Any]) -> dict[str, Any]:
    """DISCOVERED IS INDEX-QUALITY FEEDBACK: a call the run made between repository functions that
    the index's flow did not predict — an edge the index missed, or a step past the flow's depth.

    @brief Overlay.
    @return The comparison.
    """
    spans = spans_of(otlp)
    names = {s["spanId"]: s["name"] for s in spans}
    observed = [(names[s["parentSpanId"]], s["name"]) for s in spans if s["parentSpanId"] in names]
    seen = set(observed)
    want = set(expected)
    discovered = [list(pair) for pair in dict.fromkeys(p for p in observed if p not in want)]
    return {
        "steps": ["confirmed" if pair in seen else "not executed" for pair in expected],
        "discovered": discovered,
        "values": _step_values(expected, spans, names),
    }


## @brief Each predicted step's recorded values, paired in order within each (caller, callee).
## @param expected The flow's (caller, callee) steps.
## @param spans The run's spans, in recorded order.
## @param names Span id → function name.
## @return Per step `{"args", "return"}`, or None when the run made no such call.
## @version 1
## @req REQ-DDB-WIKI-049
def _step_values(expected: list[tuple[str, str]], spans: list[dict], names: dict) -> list:
    """REPLAY WITH VALUES (owner, round 5): the k-th predicted call of a pair is the k-th observed
    one, so `load → parse` twice gets each call's own values; once a pair's calls are used up a
    further predicted step gets none rather than a repeat.

    @brief Pair values with steps.
    @return Values.
    """
    queues: dict[tuple[str, str], list[dict]] = {}
    for span in spans:
        if span["parentSpanId"] in names:
            attrs = {
                a["key"]: next(iter(a["value"].values()), "") for a in span.get("attributes", [])
            }
            queues.setdefault((names[span["parentSpanId"]], span["name"]), []).append(
                {"args": attrs.get("clew.args", ""), "return": attrs.get("clew.return", "")}
            )
    return [queues[pair].pop(0) if queues.get(pair) else None for pair in expected]


## @brief Every OTLP JSON trace under the configured globs.
## @param repo_root The repository.
## @param globs The globs.
## @return (repo-relative file, document) pairs; an unreadable file is skipped with a warning.
## @version 1
## @req REQ-DDB-WIKI-036
def load_traces(repo_root: Path, globs: tuple[str, ...]) -> list[tuple[str, dict[str, Any]]]:
    """@brief Load traces. @return Pairs."""
    import logging

    root = Path(repo_root)
    out = []
    for path in sorted({p for g in globs for p in root.glob(g) if p.is_file()}):
        try:
            out.append(
                (path.relative_to(root).as_posix(), json.loads(path.read_text(encoding="utf-8")))
            )
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning("trace %s skipped: %s", path, exc)
    return out


## @brief The name of a trace's root span (the test), or "".
## @param otlp The document.
## @return The name.
## @version 1
## @req REQ-DDB-WIKI-036
def root_name(otlp: dict[str, Any]) -> str:
    """@brief Root. @return Name."""
    spans = spans_of(otlp)
    ids = {s.get("spanId") for s in spans}
    return next((s["name"] for s in spans if s.get("parentSpanId") not in ids), "")


## @brief The first failing span's exception: where and why.
## @param otlp The document.
## @return {span, line, message}, or None when nothing failed.
## @version 1
## @req REQ-DDB-WIKI-036
def failure_of(otlp: dict[str, Any]) -> dict[str, str] | None:
    """@brief Failure. @return Mapping or None."""
    for span in spans_of(otlp):
        if (span.get("status") or {}).get("code") != 2:
            continue
        event = next((e for e in span.get("events") or [] if e.get("name") == "exception"), {})
        attrs = {
            a["key"]: next(iter(a["value"].values()), "") for a in event.get("attributes") or []
        }
        return {
            "span": span["name"],
            "line": str(attrs.get("code.lineno", "")),
            "message": str(
                attrs.get("exception.message") or (span.get("status") or {}).get("message", "")
            ),
        }
    return None
