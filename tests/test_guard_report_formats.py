# SPDX-License-Identifier: MIT
"""`clew guard validate --format sarif|gitlab|github` (S1; 2.0.0).

OWNER-APPROVED 2026-11-17 (standards research, S1). The SARIF output is validated against the
OFFICIAL OASIS SARIF 2.1.0 schema, vendored at tests/data/sarif-schema-2.1.0.json (from
oasis-tcs/sarif-spec, sarif-2.1/schema/sarif-schema-2.1.0.json) so the test runs offline.

@brief Tests the guard's machine-readable violation formats.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from clew.guard.checks import Violation
from clew.guard.report_formats import fingerprint, render

_SCHEMA = Path(__file__).parent / "data" / "sarif-schema-2.1.0.json"

_VIOLATIONS = [
    Violation(
        "src/a.c",
        12,
        "version",
        "Function 'open' body changed but @version was not updated",
        "Dev::open(int)",
    ),
    Violation("src/a.c", 3, "presence", "Function 'close' has no doxygen comment", "close()"),
    Violation("src/b,c:d.py", 7, "tag", "Unknown tag @foo in run()\n100% sure", "run()"),
]


def test_sarif_validates_against_the_official_schema() -> None:
    """@brief The SARIF log is schema-valid, with a rule for every check class."""
    log = json.loads(render(_VIOLATIONS, "sarif"))
    jsonschema.validate(log, json.loads(_SCHEMA.read_text()))
    (run,) = log["runs"]
    assert {r["id"] for r in run["tool"]["driver"]["rules"]} >= {"presence", "version", "tag"}
    assert [
        r["locations"][0]["physicalLocation"]["region"]["startLine"] for r in run["results"]
    ] == [3, 12, 7]


def test_the_fingerprint_survives_a_line_move_and_separates_overloads() -> None:
    """@brief Same violation one line down: same fingerprint. Another overload: different."""
    v = _VIOLATIONS[0]
    moved = Violation(v.file, v.line + 40, v.check, v.message, v.qualified)
    overload = Violation(v.file, v.line, v.check, v.message, "Dev::open(int, int)")
    assert fingerprint(v) == fingerprint(moved)
    assert fingerprint(v) != fingerprint(overload)


def test_gitlab_code_quality_is_byte_for_byte() -> None:
    """@brief The Code Quality document for one violation, exactly."""
    v = _VIOLATIONS[1]
    assert render([v], "gitlab") == (
        "[\n"
        "  {\n"
        '    "check_name": "presence",\n'
        '    "description": "Function \'close\' has no doxygen comment",\n'
        f'    "fingerprint": "{fingerprint(v)}",\n'
        '    "location": {\n'
        '      "lines": {\n'
        '        "begin": 3\n'
        "      },\n"
        '      "path": "src/a.c"\n'
        "    },\n"
        '    "severity": "major"\n'
        "  }\n"
        "]\n"
    )


def test_github_annotations_are_byte_for_byte_and_escaped() -> None:
    """@brief `::error` lines, sorted, with `%`, newlines, `:` and `,` escaped as the runner wants."""
    assert render(_VIOLATIONS, "github") == (
        "::error file=src/a.c,line=3,title=clew guard presence::Function 'close' has no doxygen comment\n"
        "::error file=src/a.c,line=12,title=clew guard version::"
        "Function 'open' body changed but @version was not updated\n"
        "::error file=src/b%2Cc%3Ad.py,line=7,title=clew guard tag::Unknown tag @foo in run()%0A100%25 sure\n"
    )


def test_no_violations_is_an_empty_document_not_no_document() -> None:
    """@brief Zero violations: a valid empty log / empty array / no lines."""
    assert json.loads(render([], "sarif"))["runs"][0]["results"] == []
    assert json.loads(render([], "gitlab")) == []
    assert render([], "github") == ""


@pytest.mark.parametrize("fmt", ["sarif", "gitlab", "github"])
def test_validate_writes_the_format_to_stdout_and_keeps_the_exit_code(
    tmp_path, capsys, fmt
) -> None:
    """@brief The CLI prints the document on stdout and still exits 1 on a violation."""
    from clew.guard.main import main

    src = tmp_path / "m.py"
    src.write_text("def undocumented():\n    return 1\n")
    rc = main(["validate", "--no-git", "--format", fmt, str(src)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "undocumented" in out
