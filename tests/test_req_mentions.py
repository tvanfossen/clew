# SPDX-License-Identifier: MIT
"""A requirement's dossier names every indexed file line that mentions it, not only its code.

OWNER, 2026-11-04, after reStructuredText became prose (#65): a requirement from the catalog is
linked to its implementing functions through `@req` tags and to nothing else — while the design
document, the diagram page, the CMake option and the release notes that name it are exactly what
a reader asks for next. One mechanism, every indexed file: Markdown, reStructuredText, CMake,
plain text, source comments.

Two things are left out on purpose: a `@req` tag line, which is already an implementer, and the
requirements catalog itself, which names every id and would list itself under all of them.

@brief Tests for requirement mentions.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.mcp_server.tools_query import QueryTools

_CATALOG = "- id: REQ-A-001\n  title: Retry once\n"
_SOURCE = """\
/**
 * @brief Send once.
 * @req REQ-A-001
 */
int send_once(void) { return 0; }
"""
_RST = "Retry policy\n============\n\nThe sender satisfies REQ-A-001 by trying once.\n"
_CMAKE = "# REQ-A-001: no retry loop is compiled in\noption(NO_RETRY ON)\n"
_NOTES = "REQ-A-0011 is a different requirement.\n"


## @brief Build the fixture and return tools bound to it.
## @param tmp_path Pytest temporary directory.
## @return QueryTools.
## @version 1
def _tools(tmp_path: Path) -> QueryTools:
    """@brief Build. @return Tools."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "requirements.yaml").write_text(_CATALOG, encoding="utf-8")
    (repo / "src/send.c").write_text(_SOURCE, encoding="utf-8")
    (repo / "docs/design.rst").write_text(_RST, encoding="utf-8")
    (repo / "CMakeLists.txt").write_text(_CMAKE, encoding="utf-8")
    (repo / "docs/notes.md").write_text(_NOTES, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return QueryTools(lambda: out, lambda: repo)


## @brief A requirement lists the documentation and build lines that name it.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_requirement_lists_every_file_line_that_names_it(tmp_path: Path) -> None:
    """@brief design.rst:4 and CMakeLists.txt:1; not the tag, the catalog, or REQ-A-0011.
    @return None.
    @version 1
    """
    reply = _tools(tmp_path).dossier("REQ-A-001")
    mentions = {(m["file"], m["line"]) for m in reply.get("mentioned_in", [])}
    assert mentions == {("docs/design.rst", 4), ("CMakeLists.txt", 1)}, reply


## @brief An index without the mentions table reports no field, not an empty one.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_index_without_the_table_leaves_the_field_absent(tmp_path: Path) -> None:
    """ABSENT IS NOT EMPTY: an index built before this pass never looked, and `[]` would say
    "nothing mentions this requirement".

    @brief mentioned_in absent; an unmentioned id on a current index is [].
    @return None.
    @version 1
    """
    import sqlite3

    tools = _tools(tmp_path)
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM req_mentions")
    conn.commit()
    assert tools.dossier("REQ-A-001")["mentioned_in"] == []
    conn.execute("DROP TABLE req_mentions")
    conn.commit()
    conn.close()
    assert "mentioned_in" not in tools.dossier("REQ-A-001")
