# SPDX-License-Identifier: MIT
"""PEP 257 docstrings fill what doxygen left bare, and nothing else.

Doxygen stays Python's front end. A plain docstring is verbatim detail to doxygen, with no
brief and an unparsed @version; clew/pydocs.py supplies the summary line and the version
for exactly those rows. A `##` block (doxygen's own) always wins.

@brief Tests for PEP 257 docstring enrichment.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import lang_parsing_substrate as lps
import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.pydocs import harvest_docstrings, summarize
from clew.query._common import extract_version, strip_xml

SRC = '''\
## @brief Doxygen-documented.
## @version 4
def doxy():
    """Docstring that must NOT replace the doxygen brief."""
    return 1


@decorated
def pep():
    """Return the answer.

    Longer detail.

    @version 2
    @req REQ-X-001
    """
    return doxy()


def bare():
    return 2


class Thing:
    """A documented class."""

    def method(self):
        """Do the thing."""
        return pep()
'''


def test_harvest_docstrings_lines_are_the_def_lines():
    tree = lps.parse_tree("python", SRC.encode())
    found = {(kind, name): line for kind, line, name, _ in harvest_docstrings(tree)}
    lines = SRC.splitlines()

    def line_of(prefix: str) -> int:
        return next(i for i, text in enumerate(lines, 1) if text.lstrip().startswith(prefix))

    assert found == {
        ("function", "doxy"): line_of("def doxy"),
        ("function", "pep"): line_of("def pep"),
        ("class", "Thing"): line_of("class Thing"),
        ("function", "method"): line_of("def method"),
    }, "the def line, not the decorator's: that is the line doxygen records"
    assert found[("function", "pep")] == line_of("@decorated") + 1


def test_summarize_takes_the_pep257_summary_and_version():
    assert summarize("Return the answer.\n\nLonger detail.\n\n@version 2\n") == (
        "Return the answer.",
        "2",
    )
    assert summarize("Multi-line\nsummary.\n\nBody.") == ("Multi-line summary.", "")
    assert summarize("Prose.\n@brief Stated.") == ("Stated.", ""), "an explicit brief wins"


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="enriches real doxygen rows")
def test_build_fills_only_what_doxygen_left_bare(tmp_path):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "mod.py").write_text(SRC, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(out)
    rows = {
        name: (strip_xml(brief), extract_version(detail), source)
        for name, brief, detail, source in conn.execute(
            "SELECT name, briefdescription, detaileddescription, dg_source FROM memberdef "
            "WHERE kind='function'"
        )
    }
    assert rows["doxy"] == ("Doxygen-documented.", "4", "doxygen"), "a ## block is never replaced"
    assert rows["pep"] == ("Return the answer.", "2", "doxygen")
    assert rows["method"][0] == "Do the thing."
    assert rows["bare"][0] == "", "no docstring, nothing invented"
    classes = dict(
        conn.execute("SELECT name, briefdescription FROM compounddef WHERE kind='class'")
    )
    assert strip_xml(classes["mod::Thing"]) == "A documented class."
    req = conn.execute(
        "SELECT COUNT(*) FROM memberdef WHERE name='pep' AND detaileddescription LIKE '%REQ-X-001%'"
    ).fetchone()[0]
    assert req == 1, (
        "the @req stays in doxygen's verbatim detail, where the requirements pass reads it"
    )


def test_ast_rows_are_left_alone(tmp_path):
    """An 'ast' row says it has no documentation; filling one in would make that false."""
    from clew.pydocs import _enrich_one

    db = tmp_path / "x.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, file_id INT, "
        "bodyfile_id INT, line INT, briefdescription TEXT, detaileddescription TEXT, dg_source TEXT)"
    )
    conn.execute("INSERT INTO memberdef VALUES (1, 'f', 1, 1, 3, '', '', 'ast')")
    conn.execute("INSERT INTO memberdef VALUES (2, 'g', 1, 1, 9, '', '', 'doxygen')")
    assert _enrich_one(conn, "function", 1, 3, "f", "Sum.", "", True, [1]) == 0
    assert _enrich_one(conn, "function", 1, 9, "g", "Sum.", "", True, [2]) == 1
    assert Path(db).exists()


def test_rows_are_located_on_the_lookups_own_file_key():
    """A member is keyed by its body file, else its declaring file; a class by its file.

    `_enrich_one` only searches the rowids filed under its key, so a key that differs
    from its WHERE clause would silently drop rows the full scan used to find.
    """
    from clew.pydocs import _locate_rows

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE memberdef (name TEXT, file_id INT, bodyfile_id INT, line INT)")
    conn.execute("CREATE TABLE compounddef (name TEXT, file_id INT, line INT)")
    conn.execute("INSERT INTO memberdef VALUES ('decl_only', 1, 0, 3)")
    conn.execute("INSERT INTO memberdef VALUES ('decl_only_null', 1, NULL, 4)")
    conn.execute("INSERT INTO memberdef VALUES ('defined', 1, 2, 5)")
    conn.execute("INSERT INTO compounddef VALUES ('mod::C', 2, 7)")
    located = _locate_rows(conn)
    assert located == {
        ("memberdef", 1, 3): [1],
        ("memberdef", 1, 4): [2],
        ("memberdef", 2, 5): [3],
        ("compounddef", 2, 7): [1],
    }
