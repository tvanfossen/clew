# SPDX-License-Identifier: MIT
"""Python reachability seeds that no NAME pattern can express.

`reachability` seeds its BFS from two sources: functions whose name matches an
entry-point LIKE pattern, and functions with no non-fuzzy caller. Both are blind
to a Python entry point, and measurably so.

MEASURED, on a large Python codebase:
a `gui/tkinter/splash_process.py` ends in the canonical

    if __name__ == "__main__":
        _main()

and `_main` came out **orphan**. The reason is specific and not obvious: doxygen
attributes that module-level call to `_main` ITSELF, so `_main` has a non-fuzzy
incoming edge and is therefore excluded from the zero-incoming source, while its
only caller is itself — a self-loop no seed reaches. The zero-incoming
conservatism cannot help precisely because the edge exists. A real program entry
was reported dead.

TWO SOURCES, BOTH DECLARATIONS RATHER THAN GUESSES
  1. `[project.scripts]` / `[tool.poetry.scripts]` in `pyproject.toml` — the repo
     STATES that `clew.cli:main` is an entry point. Resolved against
     doxygen's fully-dotted `definition` (verified format:
     `clew.threads._SpawnHarvester.harvest`), so `clew = "…cli:main"`
     seeds `cli.main` and not the unrelated `mcp_server.server.main`.
  2. `if __name__ == "__main__":` guard bodies — the source's own statement about
     how it is invoked. A name called there is resolved to a function in the SAME
     FILE first, so a guard calling `main()` in a repo with eleven `main`s seeds
     the right one.

DELIBERATELY NOT IMPLEMENTED — subsumed, not overlooked:
  - **pytest `test_*` functions** and **decorator-registered handlers**
    (`@mcp.tool()`, `@app.route(...)`). Both were candidates, and both are
    already covered by the EXISTING zero-incoming source: a test function and a
    framework-dispatched handler have no static caller at all, so they are seeded
    before this module runs. Adding them would mean a per-file harvest stage and
    a declared passive-decorator list for zero change in output. Verified against
    both codebases' orphan lists: no test function and no decorated handler
    appears in either. If a future repo shows one, the mechanism to add is a
    seed source here, not a change to reachability.

@brief Structural Python reachability seeds (console scripts, __main__ guards).
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .pyast import dotted_name, is_python_tree, node_text, tail_name
from .threads import SCOPE_SEP_PY, _resolve_qualified_entry
from .tomlcompat import require_toml_module
from .vocabulary import STAGE_PY_ENTRIES

## The dunder a Python module compares against to detect direct execution.
_MAIN_GUARD_NAME = "__main__"
## `pyproject.toml` tables that declare console entry points. Both spellings are
## real (PEP 621 and poetry), so both are read rather than assuming one build
## backend.
_SCRIPT_TABLES = (("project", "scripts"), ("tool", "poetry", "scripts"))


## @brief Harvest the function names called inside a file's `__main__` guards.
## @param tree The parsed Python tree.
## @param src_bytes The file's raw bytes.
## @return Callee names invoked under an `if __name__ == "__main__":` guard.
## @version 1
## @req REQ-DDB-PIPE-004
def harvest_main_guard_calls(tree: Any, src_bytes: bytes) -> list[str]:
    """Finds `if` statements whose condition compares `__name__` against the
    `"__main__"` literal, then collects every call in the guard's body.

    Matching the CONDITION rather than any `if` is what keeps this from seeding
    arbitrary conditional calls; matching `__name__` by identifier rather than by
    the literal's text alone is what keeps a module that merely mentions the
    string `"__main__"` from qualifying.

    @brief Collect calls under a module's `__main__` guard.
    @return Callee names in the guard body.
    @version 1
    """
    names: list[str] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "if_statement" or not _is_main_guard(node, src_bytes):
            continue
        body = node.child_by_field_name("consequence")
        if body is not None:
            names.extend(_called_names(body, src_bytes))
    return names


## @brief True when an `if` statement's condition is the `__main__` guard.
## @param node An `if_statement` node.
## @param src_bytes The file's raw bytes.
## @return Whether the condition compares `__name__` to `"__main__"`.
## @version 1
## @dg_internal
def _is_main_guard(node: Any, src_bytes: bytes) -> bool:
    """@brief Detect the `__name__ == "__main__"` condition.

    @return True for a main guard.
    @version 1
    """
    condition = node.child_by_field_name("condition")
    if condition is None or condition.type != "comparison_operator":
        return False
    kids = condition.named_children
    texts = {node_text(k, src_bytes).strip("\"'") for k in kids}
    return "__name__" in texts and _MAIN_GUARD_NAME in texts


## @brief Every statically-named callee inside one subtree.
## @param root Node to walk.
## @param src_bytes The file's raw bytes.
## @return Bare tail names of the calls found.
## @version 1
## @dg_internal
def _called_names(root: Any, src_bytes: bytes) -> list[str]:
    """@brief Collect the tail names of every call in a subtree.

    @return Callee tail names.
    @version 1
    """
    names: list[str] = []
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call":
            continue
        dotted = dotted_name(node.child_by_field_name("function"), src_bytes)
        if dotted is not None:
            names.append(tail_name(dotted))
    return names


## @brief Per-file harvester for `__main__`-guard entry-point names.
## @version 1
class _MainGuardHarvester(Harvester):
    """Records the names a file's `__main__` guard calls. Rowid-free (names
    only), so it caches on the file's content sha like every other stage.

    Non-Python files return an empty payload rather than being skipped, because
    the harvest driver decides parseability by extension and a C file simply has
    no guard to find.

    @brief `__main__`-guard per-file harvester.
    @version 1
    """

    stage = STAGE_PY_ENTRIES
    stage_version = 1
    label = "python entries"

    ## @brief Harvest one file's `__main__`-guard callee names.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's raw bytes.
    ## @return List of callee names, empty for a non-Python file.
    ## @version 1
    ## @req REQ-DDB-PIPE-004
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        if not is_python_tree(tree):
            return []
        return harvest_main_guard_calls(tree, src_bytes)


## @brief The `__main__`-guard seed stage's harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-PIPE-003
def main_guard_harvester() -> Harvester:
    """Public factory for gh#358's shared parse pass, which warms this stage with all
    the others even though it runs last, inside the reachability seeding.

    @brief Build this stage's harvester.
    @version 1
    """
    return _MainGuardHarvester()


## @brief Read `pyproject.toml` and return its declared console-script targets.
## @param repo_root Repo root to look in.
## @return Declared targets in `module.path:function` form.
## @version 1
## @req REQ-DDB-PIPE-004
def console_script_targets(repo_root: Path | str | None) -> list[str]:
    """Absent or unparseable `pyproject.toml` yields nothing, which is the norm
    for a C repo and must never fail a build.

    @brief Read declared console-script entry points.
    @return List of `module:function` targets.
    @version 1
    """
    if repo_root is None:
        return []
    path = Path(repo_root).expanduser() / "pyproject.toml"
    doc = _read_toml(path)
    targets: list[str] = []
    for table in _SCRIPT_TABLES:
        scripts = _nested(doc, table)
        targets.extend(str(v) for v in scripts.values() if isinstance(v, str))
    return targets


## @brief Parse a TOML file into a mapping, tolerating a bad file but not a missing parser.
## @param path File to read.
## @return The parsed document, or {} when the file is absent or malformed.
## @version 2
## @dg_internal
def _read_toml(path: Path) -> dict:
    """The tolerance here is deliberate and NARROW. A repo with no
    `pyproject.toml`, or one with a syntax error in it, must not fail a build —
    that is a property of the target, and `{}` is the right answer.

    Having no TOML PARSER is not that. This used to catch `ImportError` in the
    same clause, so on Python 3.10 — where `tomllib` is not stdlib — the absent
    module was swallowed, logged as a warning and turned into `{}`, and the
    pipeline built a graph missing every `pyproject.toml` entry point while
    reporting success (gh#23). `require_toml_module` raises
    `TomlParserUnavailableError`, which is deliberately NOT an `ImportError` so
    it cannot be re-caught here by accident.

    @brief Read a TOML document; {} on a bad file, raise with no parser.
    @return Parsed mapping, or {} when the file is absent or malformed.
    @version 2
    """
    if not path.is_file():
        return {}
    toml = require_toml_module()
    try:
        with path.open("rb") as handle:
            return toml.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning("py entries: %s is unreadable (%s) — ignoring", path, exc)
        return {}


## @brief Walk a nested TOML table path, returning a mapping.
## @param doc The parsed document.
## @param keys Table path to descend.
## @return The mapping at that path, or {} when any level is missing.
## @version 1
## @dg_internal
def _nested(doc: dict, keys: tuple[str, ...]) -> dict:
    """@brief Descend a nested TOML table path.

    @return The mapping found, or {}.
    @version 1
    """
    node: Any = doc
    for key in keys:
        if not isinstance(node, dict):
            return {}
        node = node.get(key)
    return node if isinstance(node, dict) else {}


## @brief Resolve declared console-script targets to memberdef rowids.
## @param conn Open connection to the database being built.
## @param targets Targets in `module.path:function` form.
## @return Rowids of the functions those targets name.
## @version 1
## @dg_internal
def _resolve_console_scripts(conn: sqlite3.Connection, targets: list[str]) -> set[int]:
    """`module.path:function` becomes the dotted `module.path.function`, which is
    exactly the shape doxygen stores in `definition` — so the resolution is exact
    and a repo with two same-named `main`s seeds only the declared one. A target
    naming an object attribute (`pkg.mod:Class.method`) resolves through the same
    path, since the dotted form still matches.

    @brief Resolve console-script targets against doxygen `definition`.
    @return Seed rowids.
    @version 1
    """
    seeds: set[int] = set()
    for target in targets:
        module, _, attribute = target.partition(":")
        if not attribute:
            continue
        rowid = _resolve_qualified_entry(conn, f"{module}.{attribute}", SCOPE_SEP_PY)
        if rowid is not None:
            seeds.add(rowid)
    return seeds


## @brief Resolve `__main__`-guard callee names to memberdef rowids.
## @param conn Open connection to the database being built.
## @param harvested (path_rowid, names) pairs from the guard harvest.
## @return Rowids of the guarded entry functions.
## @version 1
## @dg_internal
def _resolve_guard_names(
    conn: sqlite3.Connection,
    harvested: list[tuple[int, Any]],
) -> set[int]:
    """Same-file resolution FIRST: a guard almost always calls a function its own
    module defines, and preferring that makes a `main()` guard seed the right one
    of a repo's many `main`s. Only a name absent from the file falls back to a
    globally unique match, and an ambiguous name seeds nothing rather than an
    arbitrary candidate.

    @brief Resolve guard callee names to rowids, preferring the same file.
    @return Seed rowids.
    @version 1
    """
    seeds: set[int] = set()
    for path_rowid, names in harvested:
        for name in names:
            rowid = _resolve_in_file(conn, name, path_rowid) or _resolve_unique(conn, name)
            if rowid is not None:
                seeds.add(rowid)
    return seeds


## @brief The rowid of a function with this name defined in this file.
## @param conn Open connection.
## @param name Function name.
## @param path_rowid The `path` rowid the body must live in.
## @return The rowid, or None when the file defines no such function.
## @version 1
## @dg_internal
def _resolve_in_file(conn: sqlite3.Connection, name: str, path_rowid: int) -> int | None:
    """@brief Resolve a name to a function defined in one specific file.

    @return Rowid or None.
    @version 1
    """
    row = conn.execute(
        "SELECT rowid FROM memberdef WHERE kind='function' AND name=? AND bodyfile_id=? "
        "ORDER BY (file_id = bodyfile_id) DESC, rowid LIMIT 1",
        (name, path_rowid),
    ).fetchone()
    return row[0] if row is not None else None


## @brief The rowid of a function whose name is unique in the whole index.
## @param conn Open connection.
## @param name Function name.
## @return The rowid, or None when the name is absent or ambiguous.
## @version 1
## @dg_internal
def _resolve_unique(conn: sqlite3.Connection, name: str) -> int | None:
    """Ambiguity yields None on purpose: seeding an arbitrary one of several
    same-named functions would mark a genuinely dead function live, which is the
    one direction the reachability layer promises never to get wrong.

    @brief Resolve a globally unique function name.
    @return Rowid or None.
    @version 1
    """
    rows = conn.execute(
        "SELECT DISTINCT rowid FROM memberdef WHERE kind='function' AND name=? "
        "AND file_id = bodyfile_id LIMIT 2",
        (name,),
    ).fetchall()
    return rows[0][0] if len(rows) == 1 else None


## @brief Collect the structural Python reachability seeds for a build.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for pyproject.toml and indexed paths).
## @param cache Optional incremental index cache; None disables caching.
## @return Memberdef rowids to seed the reachability BFS with.
## @version 3
## @req REQ-DDB-PIPE-004
def python_entry_seeds(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
) -> set[int]:
    """Runs before `mark_reachability` and hands it `extra_seeds`. Returns an
    empty set — costing one cheap harvest pass — for a repo with no
    `pyproject.toml` and no Python files, so a C/C++ build's seed set is
    bit-identical to before.

    @brief Compute Python entry-point seed rowids.
    @return Seed rowids (empty for a non-Python codebase).
    @version 3
    """
    conn = sqlite3.connect(str(db_path))
    scripts = _resolve_console_scripts(conn, console_script_targets(repo_root))
    guards: set[int] = set()
    ts_classes = try_import_tree_sitter()
    if ts_classes is not None:
        harvested = run_harvest(conn, repo_root, main_guard_harvester(), ts_classes, cache)
        guards = _resolve_guard_names(conn, harvested)
    conn.close()
    seeds = scripts | guards
    if seeds:
        logger.info(
            "py entries: %d reachability seeds (%d console_scripts, %d __main__ guards)",
            len(seeds),
            len(scripts),
            len(guards),
        )
    return seeds
