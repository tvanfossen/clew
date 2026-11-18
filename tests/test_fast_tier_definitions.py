# SPDX-License-Identifier: MIT
"""The fast tier accepts an added, removed or renamed function (PR1; 2.0.0).

OWNER-APPROVED 2026-11-17 (refresh-speed interjection, PR1). The fast tier refused any edit that
changed a file's set of definitions, so adding a function, the commonest structural edit, cost a
full build (5.6 to 13.8 s on the measured repositories, PR0). It now RECONCILES the edited file's
functions by identity (kind, qualified name, overload ordinal):

- a matched function keeps its rowid and only moves, as before;
- a removed one is deleted with every row that references it (`fasttier.MEMBERDEF_REFERENCES`,
  pinned below against every column of a built index);
- an added one is inserted with a PROVISIONAL rowid, named in `fast.provisional`, with its
  outgoing edges computed now. Its inbound edges wait for the full build, which the
  `derived` notice already says is pending.

A RENAME IS A REMOVAL PLUS AN ADDITION. Any other kind of definition change (a class, a variable,
a macro) still takes the full build, and says so.

@brief Tests the fast tier's definition reconciliation.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.refresh_command import refresh_main

_TS = """\
export function fetchWidget(id: string): number {
  return id.length;
}

export function renderWidget(id: string): number {
  return fetchWidget(id) + 1;
}
"""
_C = """\
static int helper(int x)
{
    return x + 1;
}

int entry(int x)
{
    return helper(x);
}
"""


def _build(repo: Path, out: Path, tier: str = "full") -> None:
    """@brief Full build, or `clew refresh` (fast tier first). @return None."""
    if tier == "full":
        _run_pipeline(
            _build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)])
        )
    else:
        assert refresh_main(["--output", str(out), "--repo-root", str(repo)]) == 0


def _repo(tmp_path: Path, rel: str, text: str) -> tuple[Path, Path]:
    """@brief One-file repo, fully built. @return (repo, db)."""
    repo = tmp_path / "repo"
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)
    out = tmp_path / "clew.db"
    _build(repo, out)
    return repo, out


def _fast(db: Path) -> dict[str, str]:
    """@brief The fast.* record. @return Mapping."""
    with sqlite3.connect(db) as conn:
        return {
            k[5:]: v
            for k, v in conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'fast.%'")
        }


def _functions(db: Path) -> dict[str, tuple[int, int]]:
    """@brief name → (bodystart, bodyend) for bodied functions. @return Mapping."""
    with sqlite3.connect(db) as conn:
        return {
            n: (int(s), int(e))
            for n, s, e in conn.execute(
                "SELECT name, bodystart, bodyend FROM memberdef WHERE kind = 'function' AND bodystart > 0 "
                "AND name NOT LIKE '#%' AND name != '__module__'"
            )
        }


def _callees(db: Path, caller: str) -> list[str]:
    """@brief One caller's callee names. @return Sorted names."""
    with sqlite3.connect(db) as conn:
        return sorted(
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT y.name FROM call_edges e JOIN memberdef x ON x.rowid = e.caller_rowid "
                "JOIN memberdef y ON y.rowid = e.callee_rowid WHERE x.name = ?",
                (caller,),
            )
        )


def _dangling(db: Path) -> list[tuple[str, str, int]]:
    """@brief Every reference to a memberdef rowid that no longer exists. @return (table, column, n)."""
    from clew.fasttier import MEMBERDEF_REFERENCES

    out = []
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table, columns in MEMBERDEF_REFERENCES.items():
            if table not in tables:
                continue
            for column in columns:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND {column} > 0 "  # noqa: S608
                    f"AND {column} NOT IN (SELECT rowid FROM memberdef)"
                ).fetchone()[0]
                if n:
                    out.append((table, column, n))
    return out


def test_an_added_function_is_refreshed_in_place(tmp_path: Path) -> None:
    """THE CASE PR1 IS FOR. Replaces the 1.3.5 test that specified a full-build fallback here.

    @brief The fast tier runs; the new function has its row, span and outgoing edges.
    """
    repo, out = _repo(tmp_path, "src/widget.ts", _TS)
    added = (
        _TS
        + "\nexport function newWidget(id: string): number {\n  return renderWidget(id) * 2;\n}\n"
    )
    (repo / "src/widget.ts").write_text(added)
    _build(repo, out, tier="fast")
    fast = _fast(out)
    assert fast.get("pending") == "1", f"the fast tier did not run: {fast}"
    assert "newWidget" in fast.get("provisional", "").split(",")
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _functions(out) == _functions(reference)
    assert _callees(out, "newWidget") == _callees(reference, "newWidget") == ["renderWidget"]
    assert _dangling(out) == []


def test_a_removed_function_leaves_no_row_and_no_dangling_reference(tmp_path: Path) -> None:
    """@brief Its rows, and every row pointing at them, are gone."""
    repo, out = _repo(tmp_path, "src/widget.ts", _TS)
    (repo / "src/widget.ts").write_text(_TS.split("export function renderWidget")[0])
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    assert "renderWidget" not in _functions(out)
    assert _dangling(out) == []


def test_a_renamed_function_is_the_old_removed_and_the_new_added(tmp_path: Path) -> None:
    """@brief Old name gone, new present at the full build's span."""
    repo, out = _repo(tmp_path, "src/widget.ts", _TS)
    (repo / "src/widget.ts").write_text(_TS.replace("renderWidget", "drawWidget"))
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _functions(out) == _functions(reference)
    assert "renderWidget" not in _functions(out)
    assert _dangling(out) == []


def test_a_c_function_added_in_place_has_its_span_and_callees(tmp_path: Path) -> None:
    """@brief The AST path (C/C++/Python), not only JS/TS."""
    repo, out = _repo(tmp_path, "src/m.c", _C)
    (repo / "src/m.c").write_text(_C + "\nint extra(int x)\n{\n    return entry(x) * 2;\n}\n")
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _functions(out)["extra"] == _functions(reference)["extra"]
    assert _callees(out, "extra") == _callees(reference, "extra") == ["entry"]
    assert _dangling(out) == []


def test_an_added_class_still_takes_the_full_build(tmp_path: Path) -> None:
    """@brief Reconciliation is for functions; any other definition change is refused."""
    repo, out = _repo(tmp_path, "src/widget.ts", _TS)
    (repo / "src/widget.ts").write_text(
        _TS + "\nexport class Gadget {\n  spin(): number { return 1; }\n}\n"
    )
    _build(repo, out, tier="auto")
    assert _fast(out).get("pending") != "1"
    assert "spin" in _functions(out)


def test_every_reference_column_is_classified(rich_db: Path) -> None:
    """PINNED: every `*_rowid` / `*_id` column of a built index is either a memberdef reference the
    removal cascades through, or named as something else. A new table cannot leave a removed
    function's rows pointing at nothing without failing here.

    @brief Reference columns are all classified.
    """
    from clew.fasttier import MEMBERDEF_REFERENCES, NOT_MEMBERDEF_COLUMNS

    unclassified = []
    with sqlite3.connect(rich_db) as conn:
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not r[0].startswith("sqlite_")
        ]
        for table in tables:
            for column in (c[1] for c in conn.execute(f"PRAGMA table_info({table})")):
                if not (column.endswith("_rowid") or column.endswith("_id")):
                    continue
                if (
                    column in MEMBERDEF_REFERENCES.get(table, ())
                    or (table, column) in NOT_MEMBERDEF_COLUMNS
                ):
                    continue
                unclassified.append(f"{table}.{column}")
    assert unclassified == []


def test_two_fast_refreshes_of_one_file_match_a_full_build(tmp_path: Path) -> None:
    """FOUND BY `incremental_probe fastcompare` (PR1). The baseline was always the last FULL build's
    content, so a second fast refresh of the same file mapped those lines onto rows the first had
    already moved (a double shift), and re-added a function the first had already added (a
    `refid` UNIQUE failure that crashed `clew refresh`). The baseline is now the content the index
    last described, full or fast.

    @brief Two consecutive line-shifting edits plus two adds: spans equal a full build's.
    """
    repo, out = _repo(tmp_path, "src/widget.ts", _TS)
    first = "// one\n// two\n" + _TS + "\nexport function addedOne(): number {\n  return 1;\n}\n"
    (repo / "src/widget.ts").write_text(first)
    _build(repo, out, tier="fast")
    second = "// zero\n" + first + "\nexport function addedTwo(): number {\n  return 2;\n}\n"
    (repo / "src/widget.ts").write_text(second)
    _build(repo, out, tier="fast")
    fast = _fast(out)
    assert fast.get("pending") == "1", f"the second fast refresh did not run: {fast}"
    assert set(fast.get("provisional", "").split(",")) == {"addedOne", "addedTwo"}
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _functions(out) == _functions(reference)
    assert _dangling(out) == []


def test_two_fast_refreshes_of_a_c_file_do_not_crash(tmp_path: Path) -> None:
    """@brief The AST writer's refid (file, line, name) must not be re-inserted."""
    repo, out = _repo(tmp_path, "src/m.c", _C)
    one = _C + "\nint extra(int x)\n{\n    return entry(x) * 2;\n}\n"
    (repo / "src/m.c").write_text(one)
    _build(repo, out, tier="fast")
    (repo / "src/m.c").write_text(one + "\nint more(int x)\n{\n    return extra(x);\n}\n")
    _build(repo, out, tier="fast")
    assert _fast(out).get("pending") == "1"
    reference = tmp_path / "full.db"
    _build(repo, reference)
    assert _functions(out)["more"] == _functions(reference)["more"]
    assert _functions(out)["extra"] == _functions(reference)["extra"]


def test_a_js_files_module_row_spans_the_new_file(tmp_path: Path) -> None:
    """FOUND BY `incremental_probe fastcompare` on mattermost-mobile (PR1). A JS/TS file's
    `__module__` row spans the whole file (its file-scope code), and the end of the file sits past
    every anchor, so the line map left it at the OLD length: 8 where a full build has 12. Any edit
    that changes a file's length did this, not only an added function.

    @brief After a fast refresh the module row ends where a full build's does.
    """
    repo, out = _repo(tmp_path, "src/widget.ts", _TS)
    (repo / "src/widget.ts").write_text(
        _TS + "\nexport function addedOne(): number {\n  return 1;\n}\n"
    )
    _build(repo, out, tier="fast")
    reference = tmp_path / "full.db"
    _build(repo, reference)
    q = "SELECT bodystart, bodyend FROM memberdef WHERE name = '__module__'"
    assert (
        sqlite3.connect(out).execute(q).fetchall()
        == sqlite3.connect(reference).execute(q).fetchall()
    )
