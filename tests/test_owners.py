# SPDX-License-Identifier: MIT
"""Who owns a file, read from the repository's own CODEOWNERS and MAINTAINERS (S2, S3; 2.0.0).

Owner-approved prior-art adoptions. Each test states one documented rule of the convention.

@brief Tests the owners layer.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.owners import codeowners_for, parse_codeowners, parse_maintainers, record_owners


def test_codeowners_last_match_wins_with_all_its_owners() -> None:
    """GitHub: "the last matching pattern takes the most precedence"; every owner on it applies.

    @brief Last match wins.
    """
    rules = parse_codeowners("* @all\n/src/ @core @lead\n*.md @docs\n")
    assert codeowners_for(rules, "src/a.c") == (["@core", "@lead"], 2)
    assert codeowners_for(rules, "src/README.md") == (["@docs"], 3)
    assert codeowners_for(rules, "tools/x.py") == (["@all"], 1)


def test_codeowners_patterns_follow_gitignore() -> None:
    """An unanchored name matches at any depth; a leading `/` anchors; `*` stays in one segment.

    @brief gitignore semantics.
    """
    rules = parse_codeowners("docs/ @d\n/build/*.c @b\nlogs @l\n")
    assert codeowners_for(rules, "docs/x/y.md") == (["@d"], 1)
    assert codeowners_for(rules, "build/a.c") == (["@b"], 2)
    assert codeowners_for(rules, "build/sub/a.c") is None
    assert codeowners_for(rules, "app/logs/out.txt") == (["@l"], 3)


def test_a_rule_with_no_owners_unsets_ownership() -> None:
    """@brief A later ownerless rule leaves the path unowned (GitHub's documented meaning)."""
    rules = parse_codeowners("* @all\n/vendor/\n")
    assert codeowners_for(rules, "vendor/lib.c") == ([], 2)


_MAINTAINERS = """\
List of maintainers
-------------------

NET DRIVERS
M:\tAda <ada@example.org>
R:\tBo <bo@example.org>
F:\tdrivers/net/
X:\tdrivers/net/wireless/

WIRELESS
M:\tCy <cy@example.org>
F:\tdrivers/net/wireless/
N:\t_wifi\\.c$
"""


def test_maintainers_every_matching_stanza_applies() -> None:
    """Kernel rules: `F: dir/` covers below; `X:` excludes; `N:` is a regex over the path; every
    stanza that matches applies.

    @brief MAINTAINERS stanzas.
    """
    stanzas = parse_maintainers(_MAINTAINERS)
    assert [s.title for s in stanzas] == ["NET DRIVERS", "WIRELESS"]
    assert [s.title for s in stanzas if s.covers("drivers/net/eth.c")] == ["NET DRIVERS"]
    assert [s.title for s in stanzas if s.covers("drivers/net/wireless/a.c")] == ["WIRELESS"]
    assert [s.title for s in stanzas if s.covers("drivers/net/my_wifi.c")] == [
        "NET DRIVERS",
        "WIRELESS",
    ]


def _index(tmp_path: Path, files: dict[str, str]) -> Path:
    """@brief A minimal index with a path table. @return The db."""
    repo = tmp_path / "repo"
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.executemany(
        "INSERT INTO path(name, type) VALUES (?, 1)",
        [(r,) for r in files if r.endswith((".c", ".py"))],
    )
    conn.commit()
    conn.close()
    return repo


def test_the_layer_records_both_sources_and_is_created_empty(tmp_path: Path) -> None:
    """@brief Rows per (file, owner, role, source); an owner-less repository still has the table."""
    repo = _index(
        tmp_path,
        {
            ".github/CODEOWNERS": "src/ @core\n",
            "MAINTAINERS": "CORE\nM:\tAda <ada@example.org>\nF:\tsrc/\n",
            "src/a.c": "int a;\n",
            "tool.py": "x = 1\n",
        },
    )
    conn = sqlite3.connect(tmp_path / "clew.db")
    assert record_owners(conn, repo) == 2
    rows = conn.execute(
        "SELECT p.name, o.owner, o.role, o.source FROM owners o JOIN path p ON p.rowid = o.path_rowid"
        " ORDER BY o.source"
    ).fetchall()
    assert rows == [
        ("src/a.c", "@core", "owner", "codeowners"),
        ("src/a.c", "Ada <ada@example.org>", "maintainer", "maintainers"),
    ]
    empty = _index(tmp_path / "e", {"src/a.c": "int a;\n"})
    conn2 = sqlite3.connect(tmp_path / "e" / "clew.db")
    assert record_owners(conn2, empty) == 0
    assert conn2.execute("SELECT count(*) FROM owners").fetchone() == (0,)


def test_a_declared_owners_file_is_read_and_a_missing_one_is_not_replaced(tmp_path: Path) -> None:
    """@brief `owners.codeowners` wins; a declared path that is not a file reads nothing."""
    repo = _index(
        tmp_path,
        {"CODEOWNERS": "* @root\n", "meta/OWNERS": "* @meta\n", "src/a.c": "int a;\n"},
    )
    conn = sqlite3.connect(tmp_path / "clew.db")
    record_owners(conn, repo, {"codeowners": "meta/OWNERS"})
    assert conn.execute("SELECT owner FROM owners").fetchall() == [("@meta",)]
    record_owners(conn, repo, {"codeowners": "missing/OWNERS"})
    assert conn.execute("SELECT count(*) FROM owners").fetchone() == (0,)


def test_the_owners_section_keys_match_the_reader() -> None:
    """@brief declaration.SECTION_KEYS['owners'] is the reader's own key set."""
    from clew.declaration import SECTION_KEYS
    from clew.owners import OWNERS_KEYS

    assert SECTION_KEYS["owners"] == OWNERS_KEYS
