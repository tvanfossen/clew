# SPDX-License-Identifier: MIT
"""The pytest plugin behind a traced test run (round 3, P4b) — loaded only in the subprocess
`clew wiki trace-run` starts, never in clew's own process. STANDALONE: it imports only the
standard library and pytest, because it is copied as a file into the TARGET repository's own
interpreter, which has pytest and need not have clew.

During each test's CALL phase a `sys.settrace` tracer records every call between functions of the
repository's own files (`CLEW_TRACE_ROOT`) as a span: its name, its file and line, the values it
was called with and returned. Comprehension, generator-expression and lambda frames (`<…>`) are
transparent — their calls belong to the function around them. The test function's own executed
lines are kept, so its assertions become checkpoints; a failing assertion's line and message are
the failure point. Everything is written as one JSON document to `CLEW_TRACE_OUT`.

@brief Record a test's calls as spans.
@version 1
"""

from __future__ import annotations

import inspect
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import pytest

## The longest repr kept for an argument or a return value; a longer one says how much it left.
_REPR_LIMIT = 2000
## The most spans one run records; past it the run says so.
_SPAN_LIMIT = 20000


## @brief One run's recording.
## @version 1
class _Recorder:
    """@brief Spans, the test's executed lines, and the failure. @version 1"""

    ## @brief Prepare a recording for one test.
    ## @param root The repository root.
    ## @param test_file The test's file.
    ## @param test_name The test function's name.
    ## @version 1
    ## @dg_internal
    def __init__(self, root: Path, test_file: Path, test_name: str) -> None:
        """@brief Store. @return None."""
        self.root = str(root.resolve())
        self.test_file = str(test_file.resolve())
        self.test_name = test_name
        self.trace_id = secrets.token_hex(16)
        self.stack: list[dict[str, Any]] = []
        self.spans: list[dict[str, Any]] = []
        self.lines: list[int] = []
        self.dropped = 0
        self.failure: dict[str, Any] | None = None

    ## @brief The global tracer: open a span for a call into a repository function.
    ## @param frame The frame.
    ## @param event The event.
    ## @param arg The event's argument.
    ## @return The local tracer, or None for a frame not traced.
    ## @version 1
    ## @dg_internal
    def tracer(self, frame: Any, event: str, arg: Any) -> Any:
        """@brief Global trace. @return Local tracer or None."""
        path = frame.f_code.co_filename
        if event != "call" or not path.startswith(self.root) or path == __file__:
            return None
        if frame.f_code.co_name.startswith("<"):
            return self.local if path == self.test_file else None
        if len(self.spans) + len(self.stack) >= _SPAN_LIMIT:
            self.dropped += 1
            return None
        self.stack.append(self._open(frame, path))
        return self.local

    ## @brief The local tracer: the test's lines, and the span's close.
    ## @param frame The frame.
    ## @param event The event.
    ## @param arg The event's argument.
    ## @return Itself.
    ## @version 1
    ## @dg_internal
    def local(self, frame: Any, event: str, arg: Any) -> Any:
        """@brief Local trace. @return Itself."""
        code = frame.f_code
        if (
            event == "line"
            and code.co_filename == self.test_file
            and code.co_name == self.test_name
        ):
            self.lines.append(frame.f_lineno)
        elif event == "return" and not code.co_name.startswith("<") and self.stack:
            span = self.stack.pop()
            span["endTimeUnixNano"] = str(time.time_ns())
            span["attributes"].append(_attr("clew.return", _repr(arg)))
            self.spans.append(span)
        return self.local

    ## @brief Open one span.
    ## @param frame The called frame.
    ## @param path Its file.
    ## @return The span.
    ## @version 1
    ## @dg_internal
    def _open(self, frame: Any, path: str) -> dict[str, Any]:
        """@brief Open. @return Span."""
        info = inspect.getargvalues(frame)
        args = ", ".join(f"{n}={_repr(info.locals.get(n))}" for n in info.args if n != "self")
        parent = self.stack[-1]["spanId"] if self.stack else ""
        rel = os.path.relpath(path, self.root)
        return {
            "traceId": self.trace_id,
            "spanId": secrets.token_hex(8),
            "parentSpanId": parent,
            "name": frame.f_code.co_name,
            "kind": 1,
            "startTimeUnixNano": str(time.time_ns()),
            "endTimeUnixNano": "",
            "attributes": [
                _attr("code.filepath", rel),
                _attr("code.lineno", str(frame.f_code.co_firstlineno)),
                _attr("code.function", frame.f_code.co_name),
                _attr("clew.args", args),
            ],
            "events": [],
            "status": {"code": 1},
        }


## @brief An OTLP string attribute.
## @param key The key.
## @param value The value.
## @return The attribute.
## @version 1
## @dg_internal
def _attr(key: str, value: str) -> dict[str, Any]:
    """@brief Attribute. @return Mapping."""
    return {"key": key, "value": {"stringValue": value}}


## @brief A value's repr, cut at `_REPR_LIMIT` with the cut stated.
## @param value The value.
## @return The text.
## @version 1
## @dg_internal
def _repr(value: Any) -> str:
    """A REPR THAT RAISES is reported as such rather than ending the run.

    @brief Repr.
    @return Text.
    """
    try:
        text = repr(value)
    except Exception as exc:  # noqa: BLE001 — a hostile __repr__ must not end the run
        text = f"<repr failed: {type(exc).__name__}>"
    if len(text) > _REPR_LIMIT:
        text = f"{text[:_REPR_LIMIT]}…({len(text) - _REPR_LIMIT} more characters)"
    return text


_RECORDING: dict[str, _Recorder] = {}


## @brief Trace the test's call phase.
## @param item The test item.
## @return None (a hook wrapper).
## @version 1
## @dg_internal
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Any:
    """@brief Trace the call. @return None."""
    root = Path(os.environ["CLEW_TRACE_ROOT"])
    name = getattr(item, "originalname", None) or item.name
    recorder = _Recorder(root, Path(str(item.path)), name)
    _RECORDING["run"] = recorder
    sys.settrace(recorder.tracer)
    try:
        yield
    finally:
        sys.settrace(None)
        while recorder.stack:
            span = recorder.stack.pop()
            span["endTimeUnixNano"] = str(time.time_ns())
            recorder.spans.append(span)


## @brief Record a failing call's assertion line and message.
## @param item The test item.
## @param call The call info.
## @return None (a hook wrapper).
## @version 1
## @dg_internal
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: Any) -> Any:
    """THE FAILURE POINT IS IN THE TEST'S OWN FILE: the deepest traceback entry there.

    @brief Note the failure.
    @return None.
    """
    outcome = yield
    report = outcome.get_result()
    recorder = _RECORDING.get("run")
    if recorder is None or report.when != "call" or not report.failed or call.excinfo is None:
        return
    here = [e for e in call.excinfo.traceback if str(e.path) == recorder.test_file]
    line = here[-1].lineno + 1 if here else 0
    recorder.failure = {"line": line, "message": str(call.excinfo.value)}


## @brief Write the recording when the session ends.
## @param session The session.
## @param exitstatus The exit status.
## @return None.
## @version 1
## @dg_internal
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """@brief Write the run. @return None."""
    recorder = _RECORDING.get("run")
    out = Path(os.environ["CLEW_TRACE_OUT"])
    if recorder is None:
        out.write_text(json.dumps({"error": "no test ran", "exitstatus": int(exitstatus)}))
        return
    if recorder.failure:
        test = next((s for s in recorder.spans if s["name"] == recorder.test_name), None)
        if test is not None:
            test["status"] = {"code": 2, "message": recorder.failure["message"]}
            test["events"].append(
                {
                    "name": "exception",
                    "timeUnixNano": test["endTimeUnixNano"],
                    "attributes": [
                        _attr("code.lineno", str(recorder.failure["line"])),
                        _attr("exception.message", recorder.failure["message"]),
                    ],
                }
            )
    out.write_text(
        json.dumps(
            {
                "exitstatus": int(exitstatus),
                "spans": recorder.spans,
                "lines": recorder.lines,
                "failure": recorder.failure,
                "dropped": recorder.dropped,
            }
        )
    )
