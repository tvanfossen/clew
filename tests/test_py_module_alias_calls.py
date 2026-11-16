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
