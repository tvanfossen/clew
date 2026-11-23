# SPDX-License-Identifier: MIT
"""The site's objects.inv lists every symbol section, not only pages and labels (P5, S8; 2.0.0).

OWNER-APPROVED 2026-11-17 (standards research, S8). `objects.inv` is Sphinx's inventory: what
intersphinx, `sphobjinv` and documentation search tools read to turn a name into a URL. The site
wrote only `std:doc` and `std:label` entries, so no tool could resolve a function to its section.
A small domain (`clew`) now registers one `clew:function` per symbol section, named
`<file>::<name>`, plus the bare name where only one file defines it.

@brief Tests symbol objects in the site's inventory.
@version 1
"""

from __future__ import annotations


import pytest

from clew.cli import _build_argparser, _run_pipeline

_A = '"""A."""\n\n\ndef helper(x):\n    """Help."""\n    return x + 1\n\n\ndef run():\n    """Run."""\n    return helper(2)\n'
_B = '"""B."""\n\n\ndef helper(y):\n    """Also help."""\n    return y\n\n\ndef other():\n    """Other."""\n    return helper(1)\n'
_WIKI = "wiki:\n  title: Inv\n  docs: [README.md]\n  flows:\n    - entry: run\n      depth: 1\n    - entry: other\n      depth: 1\n"


@pytest.fixture(scope="module")
def inventory(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, str]]:
    """@brief Build a site; read its inventory. @return {type: {name: uri}}."""
    from sphinx.util.inventory import InventoryFile

    from clew.wiki.build import build_wiki

    root = tmp_path_factory.mktemp("inv")
    repo = root / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg/__init__.py").write_text("")
    (repo / "pkg/a.py").write_text(_A)
    (repo / "pkg/b.py").write_text(_B)
    (repo / "README.md").write_text("# Inv\n")
    (repo / ".clew.yaml").write_text(_WIKI)
    db = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    html = build_wiki(repo, db, root / "out")
    with (html / "objects.inv").open("rb") as handle:
        inv = InventoryFile.load(handle, "", lambda base, uri: uri)
    return {kind: {name: entry[2] for name, entry in items.items()} for kind, items in inv.items()}


def test_every_symbol_section_is_an_object(inventory) -> None:
    """@brief file::name for each section, pointing at its page and anchor."""
    functions = inventory.get("clew:function", {})
    assert "pkg/a.py::run" in functions and "pkg/b.py::other" in functions
    assert "pkg/a.py::helper" in functions and "pkg/b.py::helper" in functions
    from clew.wiki.symbols import anchor, page_for

    assert functions["pkg/a.py::run"] == f"{page_for('pkg/a.py')}.html#{anchor('run')}"


def test_a_unique_bare_name_is_listed_and_a_shared_one_is_not(inventory) -> None:
    """@brief `run` resolves by itself; `helper`, defined in two files, only qualified."""
    functions = inventory.get("clew:function", {})
    assert "run" in functions
    assert "helper" not in functions
