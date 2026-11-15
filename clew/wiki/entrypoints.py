# SPDX-License-Identifier: MIT
"""The repository's entry points, as flows the site derives without being told.

Owner 2026-11-15: the wiki is ENTIRELY GENERATED, and two hand-declared flows for clew "should be
more comprehensive" — "entry points + declared roots (clew.yaml)". Every entry point gets a flow:

  * a CONSOLE SCRIPT in `pyproject.toml` (`[project.scripts]`, `module:function`) — titled by the
    script's name;
  * a `main` function outside test code (C, C++, Rust, Python scripts);
  * a THREAD's entry function, from the index's thread layer.

An entry is selected by its FILE as well as its name (`FlowSpec.file`): every Python `def main`
shares one name and definition. Entries in test code and entries that call nothing the index
resolved are left out — a flow of no steps is not a diagram. Roots beyond these are declared in
`wiki.flows`, and a declared flow for the same function wins.

@brief Discover entry-point flows.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from ..query._common import connect, table_exists
from .config import FlowSpec


## @brief The flows of a repository's entry points.
## @param db The index.
## @param repo_root The repository.
## @param depth The call depth each flow expands.
## @return Flow specs, scripts first, then mains, then thread entries.
## @version 1
## @req REQ-DDB-WIKI-018
def entry_point_flows(db: Path, repo_root: Path, depth: int) -> list[FlowSpec]:
    """@brief Discover entry points. @return Specs."""
    found: dict[tuple[str, str], str] = {}
    with connect(db) as conn:
        for name, rel, title in (
            *_scripts(conn, Path(repo_root)),
            *_mains(conn),
            *_thread_entries(conn),
        ):
            if (name, rel) not in found and _calls_something(conn, name, rel):
                found[(name, rel)] = title
    return [
        FlowSpec(entry=name, file=rel, depth=depth, title=title)
        for (name, rel), title in found.items()
    ]


## @brief Console scripts declared in pyproject.toml, resolved to indexed functions.
## @param conn Open connection.
## @param repo_root The repository.
## @return (function, file, title) rows.
## @version 1
## @dg_internal
def _scripts(conn: object, repo_root: Path) -> list[tuple[str, str, str]]:
    """`pkg.mod:func` IS LOOKED FOR at `pkg/mod.py`, `pkg/mod/__init__.py` and their `src/` forms;
    a script whose function the index does not hold is skipped.

    @brief Read scripts.
    @return Rows.
    """
    path = repo_root / "pyproject.toml"
    if not path.is_file():
        return []
    from ..tomlcompat import require_toml_module

    doc = require_toml_module().loads(path.read_text(encoding="utf-8"))
    scripts = (doc.get("project") or {}).get("scripts") or {}
    out = []
    for script, target in scripts.items():
        module, _, func = str(target).partition(":")
        func = func.split(".")[-1]
        base = module.replace(".", "/")
        for rel in (
            f"{base}.py",
            f"{base}/__init__.py",
            f"src/{base}.py",
            f"src/{base}/__init__.py",
        ):
            if _defined(conn, func, rel):
                out.append((func, rel, f"{script} — `{func}` ({rel})"))
                break
    return out


## @brief `main` functions outside test code.
## @param conn Open connection.
## @return (function, file, title) rows.
## @version 1
## @dg_internal
def _mains(conn: object) -> list[tuple[str, str, str]]:
    """@brief Find mains. @return Rows."""
    rows = conn.execute(
        "SELECT DISTINCT p.name FROM memberdef m JOIN path p ON p.rowid = m.file_id "
        f"WHERE m.kind = 'function' AND m.name = 'main' {_not_test(conn)} ORDER BY p.name"
    )
    return [("main", str(rel), f"`main` ({rel})") for (rel,) in rows]


## @brief Thread entry functions outside test code.
## @param conn Open connection.
## @return (function, file, title) rows.
## @version 1
## @dg_internal
def _thread_entries(conn: object) -> list[tuple[str, str, str]]:
    """@brief Find thread entries. @return Rows."""
    if not table_exists(conn, "threads"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT m.name, p.name, t.name FROM threads t "
        "JOIN memberdef m ON m.rowid = t.entry_memberdef_rowid "
        f"JOIN path p ON p.rowid = m.file_id WHERE 1 = 1 {_not_test(conn)} ORDER BY p.name, m.name"
    )
    return [(str(n), str(rel), f"thread `{t}` — `{n}` ({rel})") for n, rel, t in rows]


## @brief Whether the index holds a function of this name in this file.
## @param conn Open connection.
## @param name The function.
## @param rel The file.
## @return True when it does.
## @version 1
## @dg_internal
def _defined(conn: object, name: str, rel: str) -> bool:
    """@brief Look up. @return Defined?"""
    row = conn.execute(
        "SELECT 1 FROM memberdef m JOIN path p ON p.rowid = m.file_id "
        "WHERE m.kind = 'function' AND m.name = ? AND p.name = ? LIMIT 1",
        (name, rel),
    ).fetchone()
    return row is not None


## @brief Whether an entry calls anything the index resolved.
## @param conn Open connection.
## @param name The function.
## @param rel Its file.
## @return True when it has an outgoing call edge.
## @version 1
## @dg_internal
def _calls_something(conn: object, name: str, rel: str) -> bool:
    """@brief Has callees? @return Bool."""
    if not table_exists(conn, "call_edges"):
        return False
    row = conn.execute(
        "SELECT 1 FROM call_edges c JOIN memberdef m ON m.rowid = c.caller_rowid "
        "JOIN path p ON p.rowid = m.file_id WHERE m.name = ? AND p.name = ? "
        "AND c.source != 'binding' LIMIT 1",
        (name, rel),
    ).fetchone()
    return row is not None


## @brief A clause excluding test code, when the index has a test-scope layer.
## @param conn Open connection.
## @return SQL ("" without the layer).
## @version 1
## @dg_internal
def _not_test(conn: object) -> str:
    """@brief Clause. @return SQL."""
    if not table_exists(conn, "test_scope"):
        return ""
    return "AND p.rowid NOT IN (SELECT path_rowid FROM test_scope)"
