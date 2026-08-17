# SPDX-License-Identifier: MIT
"""Would `pip install clew` on a clean machine produce a working tool?

Every test here is about the INSTALLED artifact rather than the working tree, and
they exist because the working tree cannot tell you the answer: a warm venv has
every package any dependency ever pulled in, so an undeclared import resolves
locally and fails only for the user.

That is not hypothetical. Task #77 was `tree-sitter-python` — installed, imported,
load-bearing, undeclared — and its fix in `pyproject.toml` states the principle:
"a shipped feature must own its dependency." The principle was then applied to
that one instance and never audited for others, so `anyio` sat in exactly the same
state: imported unguarded at `mcp_server/server.py` module scope, `anyio.run(...)`
IS the server's main loop, and it arrived only transitively through `mcp`.

So `test_every_third_party_import_is_declared` is deliberately a CLASS check, not
an assertion about `anyio`. A test naming `anyio` would have passed the whole time
#77 was broken.

@brief Tests that the declared distribution matches what the code actually needs.
@version 1
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from clew.tomlcompat import require_toml_module

## This file reads `pyproject.toml`, so it needs the same parser the package does
## — and for the same reason it must not import `tomllib` directly: the declared
## floor is 3.10, where that module does not exist (gh#23). Resolved once at import
## rather than per test, so a broken install fails collection loudly.
_toml = require_toml_module()

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "clew"

## Distribution name -> the module name it actually installs, for the cases where
## they differ. Only genuinely-renamed packages belong here; an entry that merely
## papers over a MISSING dependency would defeat the test.
_DIST_TO_MODULE = {
    "pyyaml": "yaml",
    "doxygen-guard": "doxygen_guard",
    "tree-sitter": "tree_sitter",
    "tree-sitter-c": "tree_sitter_c",
    "tree-sitter-cpp": "tree_sitter_cpp",
    "tree-sitter-python": "tree_sitter_python",
}

## Imported by the package but deliberately NOT a dependency, each with the reason.
## Every entry is a claim that has to stay true, so the list is short on purpose.
_JUSTIFIED_UNDECLARED = {
    # STDLIB, but only from 3.11 — so `sys.stdlib_module_names` does not list it on
    # this project's declared 3.10 floor and the check below sees it as third-party.
    # It cannot be declared as a dependency (there is no `tomllib` distribution) and
    # it is never imported unguarded: `tomlcompat` is the single importer and falls
    # back to `tomli`, which IS declared for `python_version < "3.11"`.
    # `tomli` itself is deliberately NOT exempted here any more — it used to be, on
    # the reasoning that the fallback was "for older embedders only and never needed
    # by our own floor". gh#23 moved the floor, so that claim expired and the
    # exemption would have hidden a genuinely missing dependency on 3.10.
    "tomllib",
}


## @brief Every top-level module the package imports, statically or dynamically.
## @return Set of top-level module names.
## @version 2
def _imported_top_level() -> set[str]:
    """Parses instead of grepping, so a module named in prose or inside a
    docstring cannot register as an import — this package's docstrings discuss
    `sqlite3`, `anyio` and `tree_sitter` constantly.

    Walks the whole AST rather than only module-scope statements, because the
    imports that matter most here are FUNCTION-LOCAL: `doxygen_guard` is imported
    lazily inside three functions, and a module-scope-only scan would call it
    undeclared-and-unused and miss the real dependency entirely.

    STATIC IMPORTS ONLY, deliberately. Dynamically-loaded modules are covered by
    `test_dynamically_loaded_grammars_are_declared`, which reads the actual
    registry instead of guessing — the tree-sitter grammars are never written as an
    `import` statement, so no scan of import syntax can see them.

    An earlier version of this function tried to infer dynamic references by
    harvesting identifier-shaped string literals from any file mentioning
    `importlib`. It "worked" and was wrong: it collected `store_true`, `ERROR`,
    `init` and `doxygen` — argparse actions, log words and a binary name — because
    nothing distinguishes a module name from any other identifier-shaped string.
    A heuristic that reports a dependency on an argparse action is worse than no
    heuristic, so it was replaced by reading the registry directly.

    @brief Collect statically imported module names from the package.
    @return The set of root module names.
    @version 2
    """
    found: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


## @brief Module names the declared dependencies provide.
## @return Set of importable top-level module names.
## @version 1
def _declared_modules() -> set[str]:
    """@brief Map `project.dependencies` to the modules they install.

    @return Importable module names implied by the declared dependencies.
    @version 1
    """
    data = _toml.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    modules: set[str] = set()
    for spec in data["project"]["dependencies"]:
        dist = spec.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower()
        modules.add(_DIST_TO_MODULE.get(dist, dist.replace("-", "_")))
    return modules


def test_every_third_party_import_is_declared() -> None:
    """The class check that #77 and the `anyio` gap both needed.

    A warm development venv makes this invisible: every transitively-installed
    package imports fine locally, so the failure belongs entirely to the user who
    installs the wheel. `mcp` happens to depend on `anyio` today — but a dependency
    we rely on and do not declare is one a dependency can drop, and the server
    would stop importing at all.

    Anything genuinely intentional goes in `_JUSTIFIED_UNDECLARED` WITH its reason,
    so an exemption is a written claim rather than a silent omission."""
    stdlib = set(sys.stdlib_module_names)
    third_party = {
        name
        for name in _imported_top_level()
        if name not in stdlib and name != "clew" and not name.startswith("_")
    }
    undeclared = third_party - _declared_modules() - _JUSTIFIED_UNDECLARED

    assert undeclared == set(), (
        f"imported but not declared in pyproject dependencies: {sorted(undeclared)} — "
        f"a shipped feature must own its dependency (#77)"
    )


def test_dynamically_loaded_grammars_are_declared() -> None:
    """#77's EXACT shape, closed by reading the registry rather than inferring it.

    `tree-sitter-python` was installed, load-bearing and undeclared, and no
    import-syntax scan could ever have caught it: `harvest._TS_GRAMMARS` names the
    grammars as STRINGS and `_try_import_ts_module` loads them via `__import__`.
    Worse, that loader swallows `ImportError` and returns None, so an undeclared
    grammar does not crash — the whole AST layer for that language silently drops
    to zero rows.

    Reading the registry the shipped code actually uses means this test follows a
    new language automatically: add a grammar there and forget the dependency, and
    this fails."""
    from clew.harvest import _TS_GRAMMARS

    named = {modname for _exts, modname in _TS_GRAMMARS}
    assert named, "precondition: the grammar registry must not be empty"

    undeclared = named - _declared_modules()
    assert undeclared == set(), (
        f"grammar module(s) loaded dynamically but not declared: {sorted(undeclared)} — "
        f"_try_import_ts_module swallows ImportError, so this fails SILENTLY at runtime"
    )


def test_the_declared_dependencies_are_all_actually_used() -> None:
    """The other direction, which keeps the first test honest.

    Without it, `test_every_third_party_import_is_declared` could be satisfied
    forever by declaring packages nobody imports — and a dependency list padded to
    silence a gate is worse than the gap, because every entry is weight a consumer
    installs and a resolver has to satisfy.

    The grammar registry counts as use: those three are real dependencies that
    simply never appear in an `import` statement."""
    from clew.harvest import _TS_GRAMMARS

    used = _imported_top_level() | {modname for _exts, modname in _TS_GRAMMARS}
    unused = {mod for mod in _declared_modules() if mod not in used}
    assert unused == set(), f"declared but never imported: {sorted(unused)}"


def test_a_missing_doxygen_is_refused_not_traced_back(monkeypatch) -> None:
    """doxygen is the one prerequisite that CANNOT be a pip dependency — it is a
    C++ program shipped as a system package, and `pip install doxygen` finds no
    distribution. So on a clean machine it is the most likely thing to be missing,
    and it was the worst-handled: `subprocess.Popen` raised
    `FileNotFoundError: ... 'doxygen'` from twelve frames down, which reads as a
    crash in this tool rather than a missing prerequisite.

    Patches `shutil.which` rather than manipulating PATH so the test states its
    premise directly and cannot be affected by the runner's environment.

    Asserts the REMEDY is present, not just that something was raised: the value of
    this refusal is that it tells the reader what to install, and an error message
    without the fix is only a politer traceback."""
    import pytest

    from clew import doxygen as doxygen_module
    from clew.errors import DoxygenUnavailableError

    monkeypatch.setattr(doxygen_module.shutil, "which", lambda _name: None)

    with pytest.raises(DoxygenUnavailableError) as exc:
        doxygen_module.run_doxygen(REPO_ROOT / "nonexistent-Doxyfile", REPO_ROOT)

    message = str(exc.value)
    assert "not on PATH" in message
    assert "apt install doxygen" in message, "the refusal must carry an install command"
    assert "PyPI" in message, "it must explain WHY it is not just another dependency"


def test_console_scripts_point_at_real_callables() -> None:
    """A typo'd entry point installs cleanly and fails at first invocation, which
    is precisely the failure this release cannot afford: `clew` and
    `clew-mcp` are the whole interface, and `init` exists to be the first
    thing a new user runs.

    Resolved by IMPORTING rather than by string comparison, because the string
    matching a module path proves nothing about the attribute existing."""
    import importlib

    data = _toml.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert scripts, "the distribution must declare console scripts"

    for name, target in scripts.items():
        module_path, _, attr = target.partition(":")
        module = importlib.import_module(module_path)
        assert callable(getattr(module, attr, None)), (
            f"console script {name} -> {target} does not resolve to a callable"
        )
