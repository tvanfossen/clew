# SPDX-License-Identifier: MIT
"""A JUnit report that is not valid XML is recovered or refused by name (#72 bug 3, 2.1).

FOUND BY AN ADOPTER (#72, 2026-11-23): Ceedling copies coloured stdout (`ESC[0m`) into its JUnit,
which is not XML 1.0. `clew wiki trace --junit` died with a raw ParseError, and through
`tests.junit` every linked test read NOT_RUN. Owner Q/A 2026-11-24: in 2.1.

@brief Tests JUnit robustness.
@version 1
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from clew.wiki.evidence import parse_junit

_COLOURED = (
    '<?xml version="1.0"?><testsuite><testcase name="test_a"/>'
    '<testcase name="test_b"><failure message="\x1b[31mexpected 2\x1b[0m">'
    "\x1b[0mboom\x07</failure></testcase></testsuite>"
)


def test_terminal_colour_codes_in_a_report_are_stripped_and_said(tmp_path: Path, caplog) -> None:  # noqa: ANN001
    """@brief ANSI sequences and XML-illegal controls are removed, the count logged, results kept."""
    report = tmp_path / "ceedling.xml"
    report.write_bytes(_COLOURED.encode("utf-8"))
    with caplog.at_level(logging.WARNING):
        results = parse_junit([report])
    assert results["test_a"].status == "passed" and results["test_b"].status == "failed"
    assert "ceedling.xml" in caplog.text and "control" in caplog.text


def test_an_unreadable_report_is_refused_naming_file_and_line(tmp_path: Path) -> None:
    """@brief Never a raw ParseError: a ValueError with the file, line and column."""
    report = tmp_path / "broken.xml"
    report.write_text('<testsuite>\n<testcase name="a">\n')
    with pytest.raises(ValueError) as exc:
        parse_junit([report])
    text = str(exc.value)
    assert "broken.xml" in text and "line" in text
