# SPDX-License-Identifier: MIT
"""Does this package actually run on its DECLARED floor, Python 3.10?

`requires-python` says `>=3.10` (gh#23, a downstream repo pinned to 3.10.12 on
Ubuntu 22.04 could not install at all). A version floor is a CLAIM, and this
file is the part of that claim which can be checked from any interpreter — CI's
3.10 matrix leg checks the rest by running the whole suite there.

Two constructs blocked 3.10, and they are guarded here for opposite reasons:

`enum.StrEnum` (3.11) is an import-time `ImportError`, so its absence is loud on
its own. What is NOT loud is the SUBSTITUTION: `class X(str, Enum)` is the
obvious replacement and is not equivalent, because `StrEnum.__str__` returns the
member's VALUE while a plain mixin member renders as `SectionStatus.PROPOSED`.
Anything interpolating a status into YAML, a log line or an MCP payload would
change silently. `test_section_status_renders_as_its_value` is the test that
fails against the careless substitution.

`tomllib` (3.11) was the dangerous one, and not because it raises. Its importer
sat inside `except (OSError, ValueError, ImportError)`, so on 3.10 the missing
parser was CAUGHT, logged as a warning and turned into `{}` — the package would
have quietly stopped discovering `pyproject.toml` entry points and gone on
building a smaller graph. That is this project's recurring defect class: an
absent capability that reads as an absent finding. So the tests here assert the
distinction the handler now makes — a file that is missing or malformed still
degrades to `{}`, while having NO PARSER AT ALL raises.

@brief Tests that the 3.10 floor is real: enum rendering and toml-parser absence.
@version 1
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

from clew.propose.model import SectionStatus
from clew.errors import TomlParserUnavailableError
from clew.tomlcompat import require_toml_module, toml_module

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "clew"


## @brief Make both toml parsers unimportable for the duration of a test.
## @version 1
@pytest.fixture
def no_toml_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `None` entry in `sys.modules` makes `import x` raise ImportError, which
    is exactly the shape a 3.10 install without the `tomli` backport has.

    @brief Simulate an interpreter with neither tomllib nor tomli.
    @version 1
    """
    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", None)


# ── The enum: the substitution must not change how a status RENDERS ──────────


## @brief A status must render as its value, not as `SectionStatus.PROPOSED`.
## @version 1
def test_section_status_renders_as_its_value() -> None:
    """THE test for the StrEnum removal. Every rendering path is asserted
    separately because they go through different dunders: `str()` uses
    `__str__`, an f-string and `format()` use `__format__` (which 3.11 changed
    for mixin enums), and `%s` uses `__str__` again via the old formatter.

    A bare `class SectionStatus(str, Enum)` passes the `==` and `.value`
    assertions and FAILS the rendering ones — but NOT the same ones on every
    interpreter, which is why each path is asserted rather than one spot-checked.
    Measured on 3.10.20 / 3.11.15 / 3.12.3, the naive substitution renders
    `SectionStatus.PROPOSED` from all six paths on 3.11+, and on 3.10 from `str()`
    and `%s` ONLY — f-strings and `format()` already gave the value there. A test
    that checked only an f-string would therefore have passed on the floor
    interpreter while the bug was live on every other supported version.

    @brief Pin the rendered form of a status against a careless enum swap.
    @version 2
    """
    status = SectionStatus.PROPOSED
    ## The `%s` and `{}` templates are BOUND to names rather than written inline.
    ## Not style: ruff's UP031/UP032 rewrite a literal `"%s" % x` and
    ## `"{}".format(x)` into f-strings, and its autofix silently collapsed the
    ## `.format()` assertion into a duplicate of the f-string one — deleting a
    ## distinct rendering path from a test whose entire purpose is covering all of
    ## them. Behind a name the call still exercises the real dunder and the lint
    ## has nothing to rewrite, which beats a `noqa` this repo would have to
    ## grandfather.
    percent = "%s"
    braces = "{}"
    rendered = {
        "str()": str(status),
        "f-string": f"{status}",
        "format()": format(status),
        "%s": percent % status,
        ".format()": braces.format(status),
        "f-string with spec": f"{status:>8}".strip(),
    }
    assert rendered == dict.fromkeys(rendered, "proposed"), rendered


## @brief A status must still BE a str, comparable and usable as a key.
## @version 1
def test_section_status_is_a_string() -> None:
    """The other half of what StrEnum provided: members are real strings, so
    existing `status == "proposed"` comparisons and dict/YAML keying still work.

    @brief Members remain str instances with value equality.
    @version 1
    """
    assert isinstance(SectionStatus.PROPOSED, str)
    assert SectionStatus.PROPOSED == "proposed"
    assert SectionStatus("proposed") is SectionStatus.PROPOSED
    assert {SectionStatus.NO_CANDIDATES: 1}["no_candidates"] == 1


## @brief Every status renders as its own value — not just the one spot-checked.
## @version 1
def test_every_status_renders_as_its_value() -> None:
    """A class check rather than an assertion about PROPOSED, on the same
    reasoning `test_packaging` gives: a test naming one member would pass while
    a later member was added wrongly.

    @brief All six members render as their values.
    @version 1
    """
    for member in SectionStatus:
        assert str(member) == member.value
        assert f"{member}" == member.value


# ── The toml parser: absent parser is LOUD, absent file is not ───────────────


## @brief With no parser importable, the helper reports absence rather than lying.
## @version 1
def test_toml_module_returns_none_when_no_parser(no_toml_parser: None) -> None:
    """The low-level accessor is allowed to answer "none" — it is the CALLERS
    that must not turn that into an empty result. Kept separate from
    `require_toml_module` so both halves of the contract are pinned.

    @brief toml_module() is None when neither tomllib nor tomli imports.
    @version 1
    """
    assert toml_module() is None


## @brief A parser IS importable on a supported interpreter.
## @version 1
def test_toml_module_is_available_here() -> None:
    """The control for the test above. Without it, a helper that always returned
    None would pass the absence test and nobody would notice.

    @brief toml_module() finds a parser on this interpreter.
    @version 1
    """
    module = toml_module()
    assert module is not None
    assert hasattr(module, "load")


## @brief `require_toml_module` raises a named, actionable error, not ImportError.
## @version 1
def test_require_toml_module_raises_when_absent(no_toml_parser: None) -> None:
    """`TomlParserUnavailableError` rather than a bare ImportError because
    ImportError is what the old handler CAUGHT — a distinct type is what lets a
    caller degrade on a bad file while refusing on a broken install. The message
    must name the fix, since the only way to hit this is a 3.10 install whose
    conditional `tomli` dependency did not arrive.

    @brief Absent parser raises a named error naming `tomli`.
    @version 1
    """
    with pytest.raises(TomlParserUnavailableError) as excinfo:
        require_toml_module()
    assert "tomli" in str(excinfo.value)


## @brief py_entrypoints must NOT swallow a missing parser into {}.
## @version 1
def test_read_toml_does_not_swallow_a_missing_parser(tmp_path: Path, no_toml_parser: None) -> None:
    """The actual gh#23 defect, at the actual call site. The file here is valid
    and present, so `{}` could only mean "we could not parse it" — which on 3.10
    was reported as a warning and produced a silently smaller graph.

    @brief A readable pyproject with no parser raises instead of returning {}.
    @version 1
    """
    from clew.py_entrypoints import _read_toml

    path = tmp_path / "pyproject.toml"
    path.write_text('[project.scripts]\nfoo = "pkg.mod:main"\n', encoding="utf-8")

    with pytest.raises(TomlParserUnavailableError):
        _read_toml(path)


## @brief An absent or malformed file still degrades to {} — that part was right.
## @version 1
def test_read_toml_still_degrades_on_a_bad_file(tmp_path: Path) -> None:
    """The counterpart, and the reason the fix is a type distinction rather than
    "stop catching things": a repo with no `pyproject.toml`, or one with a
    syntax error in it, must not fail a build. Only "no parser exists" does.

    @brief Missing and malformed files remain tolerated.
    @version 1
    """
    from clew.py_entrypoints import _read_toml

    assert _read_toml(tmp_path / "absent.toml") == {}

    bad = tmp_path / "pyproject.toml"
    bad.write_text("this is not = = toml\n", encoding="utf-8")
    assert _read_toml(bad) == {}


## @brief A present, valid file still parses — the control for the two above.
## @version 1
def test_read_toml_parses_a_good_file(tmp_path: Path) -> None:
    """@brief A valid TOML document is returned as a mapping.

    @version 1
    """
    from clew.py_entrypoints import _read_toml

    path = tmp_path / "pyproject.toml"
    path.write_text('[project.scripts]\nfoo = "pkg.mod:main"\n', encoding="utf-8")
    assert _read_toml(path)["project"]["scripts"]["foo"] == "pkg.mod:main"


# ── The regression guard: no NEW 3.11-only construct may enter the package ───

## Constructs that do not exist on the declared floor. Names are matched against
## `module.attr` accesses and `from module import attr`; the two that actually
## bit us (StrEnum, tomllib) are joined by the ones this issue guessed at, so a
## future edit reintroducing any of them fails here rather than in a consumer's
## install.
_FORBIDDEN_ATTRS = {
    ("enum", "StrEnum"),
    ("enum", "ReprEnum"),
    ("typing", "Self"),
    ("typing", "LiteralString"),
    ("typing", "Never"),
    ("typing", "assert_never"),
    ("typing", "assert_type"),
    ("typing", "override"),
    ("asyncio", "TaskGroup"),
    ("asyncio", "timeout"),
    ("datetime", "UTC"),
    ("contextlib", "chdir"),
    ("hashlib", "file_digest"),
    ("itertools", "batched"),
}

## `tomllib` is importable ONLY from the compatibility shim, which is the whole
## point of extracting it: two independent importers is how one of them ends up
## without the fallback.
_TOML_SHIM = "tomlcompat.py"


## @brief Collect every 3.11+-only construct used in one module.
## @param path The module to scan.
## @return List of "line: what" strings, empty when the module is 3.10-clean.
## @version 1
def _too_new_constructs(path: Path) -> list[str]:
    """Deliberately AST-based rather than a text grep: a grep for `StrEnum`
    matches this test file's own tables and the prose explaining them, which is
    how a guard ends up either false-positive or switched off.

    @brief AST-scan one module for constructs newer than the declared floor.
    @return Human-readable hits, empty if clean.
    @version 1
    """
    hits: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        hits.extend(_hits_for_node(node, path))
    return hits


## @brief Report the too-new constructs a single AST node represents.
## @param node The node to inspect.
## @param path Module being scanned, so the toml shim can exempt itself.
## @return Hit strings for this node.
## @version 2
def _hits_for_node(node: ast.AST, path: Path) -> list[str]:
    """Split out of `_too_new_constructs` to keep both under the complexity
    ceiling; the import cases and the attribute case share nothing but the
    output shape. Three returns, which is the repo's ceiling — the attribute case
    is delegated rather than inlined as a fourth.

    @brief Per-node dispatch of the too-new-construct check.
    @return Hit strings for this node.
    @version 2
    """
    if isinstance(node, ast.Import):
        return [
            f"{node.lineno}: import {a.name}"
            for a in node.names
            if a.name == "tomllib" and path.name != _TOML_SHIM
        ]
    if isinstance(node, ast.ImportFrom):
        return _import_from_hits(node, path)
    return _attribute_hits(node)


## @brief Report a too-new `module.attr` access.
## @param node The node to inspect.
## @return Hit strings, empty when the node is not a forbidden attribute access.
## @version 1
def _attribute_hits(node: ast.AST) -> list[str]:
    """@brief Check a `module.attr` access against the forbidden table.

    @return Hit strings.
    @version 1
    """
    if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
        return []
    key = (node.value.id, node.attr)
    return [f"{node.lineno}: {node.value.id}.{node.attr}"] if key in _FORBIDDEN_ATTRS else []


## @brief Report too-new names pulled in by a `from X import Y`.
## @param node The import node.
## @param path Module being scanned.
## @return Hit strings.
## @version 1
def _import_from_hits(node: ast.ImportFrom, path: Path) -> list[str]:
    """@brief Check a from-import against the forbidden table.

    @return Hit strings.
    @version 1
    """
    module = node.module or ""
    if module == "tomllib" and path.name != _TOML_SHIM:
        return [f"{node.lineno}: from tomllib import ..."]
    return [
        f"{node.lineno}: from {module} import {a.name}"
        for a in node.names
        if (module, a.name) in _FORBIDDEN_ATTRS
    ]


## @brief No shipped module may use a construct newer than the declared floor.
## @version 1
def test_package_uses_no_construct_newer_than_the_floor() -> None:
    """A CLASS check over the whole shipped package, not an assertion about the
    two constructs that were found. gh#23's scan was run by hand and its
    "exactly two blockers" finding was already a month stale by the time it was
    acted on — eleven modules had been added since. This is that scan, run every
    commit.

    It guards the package only. `tests/` is not shipped and CI runs it on 3.10
    directly, which is a stronger check than a scan.

    @brief AST-scan the whole package for post-3.10 constructs.
    @version 1
    """
    offenders: dict[str, list[str]] = {}
    for module in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in module.parts:
            continue
        hits = _too_new_constructs(module)
        if hits:
            offenders[str(module.relative_to(REPO_ROOT))] = hits

    assert not offenders, (
        "constructs unavailable on the declared 3.10 floor "
        f"(see gh#23 and clew/tomlcompat.py): {offenders}"
    )


## @brief The floor the package declares must be the one this file guards.
## @version 1
def test_declared_floor_is_310() -> None:
    """Ties the construct guard above to `pyproject.toml`, so raising the floor
    back to 3.11 does not leave a test silently enforcing a rule nobody wants any
    more — and so lowering it further fails loudly rather than being half-true.

    @brief requires-python still declares the 3.10 floor this file assumes.
    @version 1
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in text


## @brief `tomli` must be declared as a conditional dependency for 3.10.
## @version 1
def test_tomli_is_a_conditional_dependency() -> None:
    """Without the marker, `tomli` would install on 3.11+ too — where it is dead
    weight — and without the dependency at all, every 3.10 install would hit
    `TomlParserUnavailableError` on its first build. The metadata and the code
    have to agree, and this is the assertion that they do.

    @brief pyproject pins tomli behind `python_version < "3.11"`.
    @version 1
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'tomli>=2; python_version < "3.11"' in text


## @brief CI must actually RUN the suite on every version the metadata claims.
## @version 2
def test_ci_matrix_covers_every_advertised_version() -> None:
    """gh#23's own condition on landing, made mechanical. Widening
    `requires-python` and the trove classifiers without a CI leg is a claim nobody
    checks — which is exactly how the unbounded `mcp>=1.28` shipped a broken
    install while 606 tests passed on a warm developer venv (gh#22).

    DERIVED FROM THE CLASSIFIERS, not a hardcoded list, and that is the whole
    point. The previous version asserted only that `"3.10"` appeared in the
    workflow, so dropping 3.11 from the matrix while leaving its classifier in
    place would have passed — the exact hole this test's own docstring described.
    A hardcoded expected list would reintroduce it the next time the supported
    set moves.

    Asserts one direction only: every ADVERTISED version must be RUN. A matrix
    leg with no classifier is running more than we claim, which is harmless.

    @brief Every `Programming Language :: Python :: 3.x` classifier has a matrix leg.
    @version 2
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    advertised = re.findall(r"Programming Language :: Python :: (3\.\d+)", pyproject)
    assert advertised, "no versioned Python classifier found — the scan matched nothing"

    unsubstantiated = [version for version in advertised if f'"{version}"' not in workflow]
    assert unsubstantiated == [], (
        f"advertised in pyproject classifiers but absent from the ci.yml matrix: {unsubstantiated}"
    )
