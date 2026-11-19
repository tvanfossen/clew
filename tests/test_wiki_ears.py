# SPDX-License-Identifier: MIT
"""EARS pattern badge: opt-in, never a gate (S9; owner-approved 2026-11-17).

@brief Tests the EARS classifier, its badge and its check notes.
@version 1
"""

from __future__ import annotations

import pytest

from clew.wiki.ears import ears_pattern


@pytest.mark.parametrize(
    ("statement", "pattern"),
    [
        ("The loader shall parse every item once.", "ubiquitous"),
        ("When a link drops, the client shall retry three times.", "event-driven"),
        ("While the cache is warm, the build shall skip doxygen.", "state-driven"),
        ("If the index is stale, then the server shall say so.", "unwanted"),
        ("Where a catalogue is declared, the wiki shall draw the product tree.", "optional"),
        ("While idle, when a file changes, the watcher shall refresh.", "complex"),
    ],
)
def test_each_ears_pattern_is_recognised(statement: str, pattern: str) -> None:
    """@brief The five patterns and their combination."""
    assert ears_pattern(statement) == pattern


@pytest.mark.parametrize(
    "statement",
    [
        "Load the data",
        "Every item is parsed once, then the load finishes.",
        "If the index is stale, the server shall say so.",
        "",
    ],
)
def test_a_statement_in_no_pattern_is_none(statement: str) -> None:
    """@brief No shall clause, or an `If` without its `then`: None."""
    assert ears_pattern(statement) is None


def _config(tmp_path, text: str):
    """@brief Load a `wiki:` section from a .clew.yaml. @return (config, problems)."""
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text(text)
    return load_wiki_config(tmp_path, None)


def test_ears_is_off_unless_declared(tmp_path) -> None:
    """@brief Default: off."""
    config, problems = _config(tmp_path, "wiki:\n  title: T\n")
    assert config.ears is False and problems == []


def test_wiki_check_ears_turns_it_on(tmp_path) -> None:
    """@brief `wiki.check.ears: true`."""
    config, problems = _config(tmp_path, "wiki:\n  check: {ears: true}\n")
    assert config.ears is True and problems == []


def test_a_non_boolean_ears_is_refused_by_name(tmp_path) -> None:
    """@brief `ears: "yes"` is a problem naming the key."""
    _config_, problems = _config(tmp_path, "wiki:\n  check: {ears: 'yes'}\n")
    assert any("wiki.check.ears" in p for p in problems), problems


def test_check_notes_name_each_requirement_in_no_pattern(tmp_path) -> None:
    """@brief Notes come from the index's requirements table, full statement included."""
    import sqlite3

    from clew.wiki.ears import ears_notes

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE requirements (id TEXT, acceptance TEXT, title TEXT)")
    conn.executemany(
        "INSERT INTO requirements VALUES (?, ?, ?)",
        [("REQ-A-1", "The loader shall parse once.", "Load"), ("REQ-B-1", "", "Load the data")],
    )
    conn.commit()
    conn.close()
    assert ears_notes(db, True) == ["note: REQ-B-1 is in no EARS pattern: 'Load the data'"]
    assert ears_notes(db, False) == []
