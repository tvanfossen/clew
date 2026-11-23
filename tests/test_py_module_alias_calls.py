# SPDX-License-Identifier: MIT
"""Python call edges through module aliases, and bindings a local shadows (round 3, P0).

Found by the wiki round-3 exploration (2026-11-15): clew's own MCP `dossier` flow stopped at the
server, because `from ..query import export as _export; _export.subject_payload(x)` made NO edge —
the harvester recorded the receiver `_export` but nothing told the resolver it names a MODULE the
file imports. Every call through a module alias (relative or absolute) was dropped, which also
cost agents the callers/callees of every function reached that way.

And a keyword argument naming a PARAMETER (`run(cwd=repo_root)` inside `def _commit(repo_root)`)
was recorded as a function binding and resolved to a pytest fixture of the same name.

@brief Tests for module-alias call resolution and shadowed keyword bindings.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_FILES = {
    "pkg/__init__.py": "",
    "pkg/query/__init__.py": "",
    "pkg/server/__init__.py": "",
    "pkg/query/export.py": 'def subject_payload(x):\n    """Payload."""\n    return x\n',
    "pkg/other/__init__.py": "",
    "pkg/other/export.py": 'def subject_payload(x):\n    """A namesake elsewhere."""\n    return 0\n',
    "pkg/server/tools.py": (
        "from ..query import export as _export\n"
        "import pkg.query.export as ex2\n"
        "from pkg.query.export import subject_payload as sp\n\n\n"
        "class Tools:\n"
        '    """Tools."""\n\n'
        "    def dossier(self, x):\n"
        '        """Dossier."""\n'
        "        return _export.subject_payload(x)\n\n\n"
        "def absolute(x):\n"
        '    """Absolute alias."""\n'
        "    return ex2.subject_payload(x)\n\n\n"
        "def not_a_module(x):\n"
        '    """`sp` is a function, not a module: `sp.subject_payload` is no call of it."""\n'
        "    return sp.subject_payload(x)\n"
    ),
    "pkg/server/runner.py": (
        "import subprocess\n\n\n"
        "def commit(repo_root):\n"
        '    """The parameter is passed along, not a function."""\n'
        '    return subprocess.run(["git"], cwd=repo_root)\n\n\n'
        "def handler():\n"
        '    """A real handler."""\n'
        "    return 1\n\n\n"
        "def register(app):\n"
        '    """A real binding."""\n'
        "    return app.add(func=handler)\n\n\n"
        "def item():\n"
        '    """A function a comprehension variable shares a name with."""\n'
        "    return 2\n\n\n"
        "def listing(items):\n"
        '    """The comprehension variable is passed along."""\n'
        "    return [dict(v=item) for item in items]\n"
    ),
    ## Round 5 (4d-0): an alias of a PACKAGE, whose `__init__` re-exports from a submodule.
    "pkg/api/__init__.py": "from .impl import run\n",
    "pkg/api/impl.py": 'def run(x):\n    """Run."""\n    return x\n',
    "pkg/elsewhere.py": 'def run(x):\n    """A namesake outside the package."""\n    return 0\n',
    "pkg/dup/__init__.py": "",
    "pkg/dup/a.py": 'def go():\n    """One go."""\n    return 1\n',
    "pkg/dup/b.py": 'def go():\n    """Another go."""\n    return 2\n',
    "pkg/server/uses.py": (
        "from .. import api as a\n"
        "from .. import dup as d\n\n\n"
        "def use(x):\n"
        '    """Calls through a package alias."""\n'
        "    return a.run(x)\n\n\n"
        "def both():\n"
        '    """Two candidates inside the package: no guess."""\n'
        "    return d.go()\n"
    ),
    ## Round 5 (W5, agent C's audit): an ABSOLUTE import of a module the repository does not
    ## own (stdlib `json`) must not land in a same-named directory deep in the tree.
    "app2/main.py": 'import json\n\n\ndef read(t):\n    """Reads."""\n    return json.loads(t)\n',
    "vendor/json/decoder.py": 'def loads(s):\n    """A copy, not the stdlib."""\n    return s\n',
    "tests/conftest.py": (
        "import pytest\n\n\n"
        "@pytest.fixture\n"
        "def repo_root():\n"
        '    """A fixture whose name a parameter shares."""\n'
        '    return "."\n'
    ),
}


## @brief The fixture repository, indexed.
## @param tmp_path_factory Pytest's factory.
## @return The index path.
## @version 1
@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build. @return Index."""
    root = tmp_path_factory.mktemp("alias")
    repo = root / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


def _edges(db: Path) -> set[tuple[str, str, str, str]]:
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT a.name, b.name, p.name, c.confidence FROM call_edges c "
        "JOIN memberdef a ON a.rowid = c.caller_rowid JOIN memberdef b ON b.rowid = c.callee_rowid "
        "JOIN path p ON p.rowid = b.file_id"
    ).fetchall()
    conn.close()
    return {(str(a), str(b), str(f), str(c)) for a, b, f, c in rows}


def test_a_call_through_a_relative_module_alias_resolves(db: Path) -> None:
    """`from ..query import export as _export` names pkg/query/export.py — not the namesake in
    pkg/other — so the edge is RESOLVED, to that file's function only.

    @brief Relative module alias.
    """
    edges = _edges(db)
    assert ("dossier", "subject_payload", "pkg/query/export.py", "resolved") in edges
    assert not any(a == "dossier" and f == "pkg/other/export.py" for a, _b, f, _c in edges)


def test_a_call_through_an_absolute_module_alias_resolves(db: Path) -> None:
    """@brief `import pkg.query.export as ex2; ex2.subject_payload()`."""
    assert ("absolute", "subject_payload", "pkg/query/export.py", "resolved") in _edges(db)


def test_an_alias_of_a_function_is_not_a_module(db: Path) -> None:
    """NO FILE BEARS THE PATH `pkg/query/export/subject_payload`, so the alias names no module and
    nothing is resolved through it — refused, never guessed.

    @brief A function alias resolves nothing as a module.
    """
    assert not any(a == "not_a_module" and c == "resolved" for a, _b, _f, c in _edges(db))


def test_a_keyword_argument_naming_a_parameter_is_not_a_binding(db: Path) -> None:
    """THE OWNER-VISIBLE DEFECT: `cwd=repo_root` inside `def commit(repo_root)` passes the
    PARAMETER along; it was recorded as a function binding and resolved to the pytest fixture
    `repo_root` in tests/conftest.py. A genuine binding (`func=handler`) is still recorded.

    @brief Shadowed keyword bindings.
    """
    edges = _edges(db)
    assert not any(a == "commit" and b == "repo_root" for a, b, _f, _c in edges)
    assert not any(a == "listing" and b == "item" for a, b, _f, _c in edges)
    assert any(a == "register" and b == "handler" for a, b, _f, _c in edges)


def test_a_call_through_a_package_alias_resolves_to_its_re_export(db: Path) -> None:
    """FOUND BY THE ROUND-5 WIKI (owner 2026-11-17: "is there not a single caller of cap at depth
    that is in the master flow?"): `from .. import query as q; q.dossier(...)` made NO edge, so
    every master flow through an MCP tool stopped at the query boundary. The alias names a
    PACKAGE; `q.dossier` is the package's re-export of a function defined in one of its modules.
    The one candidate inside that package is the callee — never the namesake outside it.

    @brief Package alias → the function inside the package.
    """
    edges = _edges(db)
    assert ("use", "run", "pkg/api/impl.py", "resolved") in edges
    assert not any(a == "use" and f == "pkg/elsewhere.py" for a, _b, f, _c in edges)


def test_a_package_alias_with_two_candidates_inside_resolves_nothing(db: Path) -> None:
    """@brief Two `go`s inside the package: refused, never guessed."""
    assert not any(a == "both" and c == "resolved" for a, _b, _f, c in _edges(db))


def test_an_absolute_import_never_lands_in_a_same_named_directory_deep_in_the_tree(
    db: Path,
) -> None:
    """FOUND BY AGENT C'S AUDIT OF 4d-0 (2026-11-17): the package-alias rule matched `/<stem>/`
    anywhere in a path, so `import json; json.loads()` resolved to `vendor/json/decoder.py`. A
    package alias resolves inside a package only when the import is RELATIVE (anchored at the
    caller's package) or the absolute package sits at the repository root.

    @brief No tree-wide suffix match for an absolute package.
    """
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT a.name, b.name FROM call_edges c JOIN memberdef a ON a.rowid = c.caller_rowid "
        "JOIN memberdef b ON b.rowid = c.callee_rowid WHERE c.source != 'doxygen_sqlite'"
    ).fetchall()
    conn.close()
    assert ("read", "loads") not in {(str(a), str(b)) for a, b in rows}
