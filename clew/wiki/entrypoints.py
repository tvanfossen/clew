# SPDX-License-Identifier: MIT
"""The repository's entry points, as flows the site derives without being told.

Owner 2026-11-15: the wiki is ENTIRELY GENERATED, and two hand-declared flows for clew "should be
more comprehensive" — "entry points + declared roots (clew.yaml)". Every entry point gets a flow:

  * a CONSOLE SCRIPT in `pyproject.toml` (`[project.scripts]` or `[tool.poetry.scripts]`,
    `module:function`) — titled by the script's name;
  * a `main` or `app_main` function outside test code (C, C++, Rust, Python scripts), and any
    function a declared `entry_patterns` names (2.0.0, W3);
  * a THREAD's entry function, from the index's thread layer.

An entry is selected by its FILE as well as its name (`FlowSpec.file`): every Python `def main`
shares one name and definition. Entries in test code and entries that call nothing the index
resolved are left out — a flow of no steps is not a diagram. Roots beyond these are declared in
`wiki.flows`, and a declared flow for the same function wins.

@brief Discover entry-point flows.
@version 2
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
## v2: thread entries carry the `threads` role; the build classifies the rest (P1e).
## v3: declared entry patterns and the platform facts, not only `main` (2.0.0, W3)
## @version 3
## @req REQ-DDB-WIKI-018
def entry_point_flows(db: Path, repo_root: Path, depth: int) -> list[FlowSpec]:
    """@brief Discover entry points. @return Specs."""
    found: dict[tuple[str, str], tuple[str, str]] = {}
    with connect(db) as conn:
        for (name, rel, title), role in (
            *((s, "") for s in _scripts(conn, Path(repo_root))),
            *((m, "") for m in _mains(conn, Path(repo_root))),
            *((e, "threads") for e in _thread_entries(conn)),
        ):
            if (name, rel) not in found and _calls_something(conn, name, rel):
                found[(name, rel)] = (title, role)
    return [
        FlowSpec(entry=name, file=rel, depth=depth, title=title, role=role)
        for (name, rel), (title, role) in found.items()
    ]


## @brief Console scripts declared in pyproject.toml, resolved to indexed functions.
## @param conn Open connection.
## @param repo_root The repository.
## @return (function, file, title) rows.
## v2 (2.0.0, D8/W4): read by `py_entrypoints.console_scripts`, so Poetry's table counts too.
## @version 2
## @dg_internal
def _scripts(conn: object, repo_root: Path) -> list[tuple[str, str, str]]:
    """`pkg.mod:func` IS LOOKED FOR at `pkg/mod.py`, `pkg/mod/__init__.py` and their `src/` forms;
    a script whose function the index does not hold is skipped.

    @brief Read scripts.
    @return Rows.
    """
    from ..py_entrypoints import console_scripts

    scripts = console_scripts(repo_root)
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


## @brief Entry functions outside test code: the platform facts and the declared patterns.
## @param conn Open connection.
## @param repo_root The repository.
## @return (function, file, title) rows.
## v2 (round 4): the file is the one holding the body, not the declaration.
## v3 (2.0.0, W3): `reachability.ENTRY_PATTERN_FACTS` (main, app_main) and the repository's
## `entry_patterns`, not only `main`.
## @version 3
## @dg_internal
def _mains(conn: object, repo_root: Path) -> list[tuple[str, str, str]]:
    """THE FACTS AND THE DECLARATION, NOT THE GUESSES. Liveness seeds on the name heuristics too
    (`%_cb`, `%callback%`), where a false positive only keeps a function alive; as flows they
    would draw every callback as an entry point.

    @brief Find entry functions.
    @return Rows.
    """
    from ..reachability import ENTRY_PATTERN_FACTS

    patterns = list(
        dict.fromkeys([*ENTRY_PATTERN_FACTS, *_declared_entry_patterns(conn, repo_root)])
    )
    clause = " OR ".join(["m.name LIKE ?"] * len(patterns))
    rows = conn.execute(
        "SELECT DISTINCT m.name, p.name FROM memberdef m JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "  # noqa: S608
        f"WHERE m.kind = 'function' AND ({clause}) {_not_test(conn)} ORDER BY p.name, m.name",
        patterns,
    )
    return [(str(n), str(rel), f"`{n}` ({rel})") for n, rel in rows]


## @brief The entry patterns the repository or its operator stated.
## @param conn Open connection.
## @param repo_root The repository.
## @return LIKE patterns: an explicit statement recorded by the build, else the declaration's.
## @version 1
## @dg_internal
def _declared_entry_patterns(conn: object, repo_root: Path) -> list[str]:
    """THE BUILD'S OWN TIERS: tier 1 (`--entry-patterns`) is recorded in `build_meta`, tier 2 is
    the `.clew.yaml`; the built-in heuristics are neither.

    @brief Read stated entry patterns.
    @return Patterns.
    """
    from ..declaration import SECTION_ENTRY_PATTERNS, load_declaration
    from ..tiers import EXPLICIT_KEY, OPTIONS_META_PREFIX, VALUE_SEPARATOR

    row = None
    if table_exists(conn, "build_meta"):
        row = conn.execute(
            "SELECT value FROM build_meta WHERE key = ?",
            (f"{OPTIONS_META_PREFIX}.{SECTION_ENTRY_PATTERNS}.{EXPLICIT_KEY}",),
        ).fetchone()
    if row and row[0]:
        return [p for p in str(row[0]).split(VALUE_SEPARATOR) if p]
    try:
        declared = load_declaration(repo_root).get(SECTION_ENTRY_PATTERNS) or []
    except Exception:  # a malformed declaration is the build's to refuse, not the site's
        declared = []
    return [str(p) for p in declared]


## @brief Thread entry functions outside test code.
## @param conn Open connection.
## @return (function, file, title) rows.
## v2 (round 4): the file is the one holding the body, not the declaration.
## @version 2
## @dg_internal
def _thread_entries(conn: object) -> list[tuple[str, str, str]]:
    """@brief Find thread entries. @return Rows."""
    if not table_exists(conn, "threads"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT m.name, p.name, t.name FROM threads t "
        "JOIN memberdef m ON m.rowid = t.entry_memberdef_rowid "
        f"JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        f"WHERE 1 = 1 {_not_test(conn)} ORDER BY p.name, m.name"
    )
    return [(str(n), str(rel), f"thread `{t}` — `{n}` ({rel})") for n, rel, t in rows]


## @brief Whether the index holds a function of this name in this file.
## @param conn Open connection.
## @param name The function.
## @param rel The file.
## @return True when it does.
## v2 (round 4): the file is the one holding the body, not the declaration.
## @version 2
## @dg_internal
def _defined(conn: object, name: str, rel: str) -> bool:
    """@brief Look up. @return Defined?"""
    row = conn.execute(
        "SELECT 1 FROM memberdef m JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "WHERE m.kind = 'function' AND m.name = ? AND p.name = ? LIMIT 1",
        (name, rel),
    ).fetchone()
    return row is not None


## @brief Whether an entry calls anything the index resolved.
## @param conn Open connection.
## @param name The function.
## @param rel Its file.
## @return True when it has an outgoing call edge.
## v2 (round 4): the file is the one holding the body, not the declaration.
## @version 2
## @dg_internal
def _calls_something(conn: object, name: str, rel: str) -> bool:
    """@brief Has callees? @return Bool."""
    if not table_exists(conn, "call_edges"):
        return False
    row = conn.execute(
        "SELECT 1 FROM call_edges c JOIN memberdef m ON m.rowid = c.caller_rowid "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.name = ? AND p.name = ? "
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
