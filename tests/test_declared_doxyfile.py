# SPDX-License-Identifier: MIT
"""A `doxyfile:` in the checked-in `.clew.yaml` is read, and OVERVIEW's example is loadable (R5-CFG F2/F3).

FOUND BY THE 2.0.0 CONFIG REVIEW (agent A, vetted, owner-approved). `doxyfile:` was a known
section — it passed the unknown-section refusal — but only the tier-1 route (`--declare`, MCP
`options`) ever applied it. A repo shaped like Mbed-TLS (`doxygen/mbedtls.doxyfile`, outside what
discovery reaches) that wrote the documented line got discovery or synthesis instead: a well-formed
index of a different file set, the failure `PATH_OPTIONS_MUST_EXIST` exists to prevent. And the only
reference for the declaration sections, OVERVIEW.md's example, had three wrong lines.

@brief Tests the in-tree Doxyfile declaration and the documented example block.
@version 1
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clew.declaration import DeclarationError, declared_event_tags, load_declaration

REPO = Path(__file__).resolve().parent.parent


def _resolve(tmp_path: Path, declaration: str, doxyfile_flag: str | None = None) -> Path:
    """@brief Resolve the build's Doxyfile for a repo with this declaration. @return The Doxyfile."""
    from clew.cli import _build_argparser, _resolve_doxyfile_and_root

    (tmp_path / ".clew.yaml").write_text(declaration, encoding="utf-8")
    argv = ["--output", str(tmp_path / "out.db"), "--repo-root", str(tmp_path)]
    args = _build_argparser().parse_args(argv)
    ## Tier 1 (`--declare` / MCP `options`) lands on this dest; there is no `--doxyfile` flag.
    args.doxyfile = doxyfile_flag
    return _resolve_doxyfile_and_root(args, tmp_path / "out.db")[0]


def test_an_in_tree_doxyfile_declaration_is_the_doxyfile(tmp_path: Path) -> None:
    """F3: the declared file is used, not discovery, and a tier-1 statement still wins.

    @brief The checked-in `doxyfile:` applies; tier 1 outranks it.
    """
    (tmp_path / "doxygen").mkdir()
    declared = tmp_path / "doxygen" / "project.doxyfile"
    declared.write_text("INPUT = src\n", encoding="utf-8")
    (tmp_path / "Doxyfile").write_text("INPUT = .\n", encoding="utf-8")
    assert _resolve(tmp_path, "doxyfile: doxygen/project.doxyfile\n") == declared.resolve()
    flag = tmp_path / "Doxyfile"
    assert _resolve(tmp_path, "doxyfile: doxygen/project.doxyfile\n", str(flag)) == flag.resolve()


def test_a_declared_doxyfile_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    """A missing declared Doxyfile changes WHICH SOURCE is indexed, so it is refused at the
    declaration rather than falling through to synthesis — the tier-1 rule, in-tree.

    @brief A missing declared Doxyfile is refused, naming it.
    """
    with pytest.raises(DeclarationError, match="doxygen/missing.doxyfile"):
        _resolve(tmp_path, "doxyfile: doxygen/missing.doxyfile\n")


def test_a_declared_doxyfile_outside_the_repo_is_refused(tmp_path: Path) -> None:
    """@brief A declared path escaping the repository is refused, like every declared path."""
    outside = tmp_path.parent / "elsewhere.doxyfile"
    outside.write_text("INPUT = .\n", encoding="utf-8")
    with pytest.raises(DeclarationError, match="doxyfile"):
        _resolve(tmp_path, f"doxyfile: {outside}\n")


def test_overviews_declaration_example_loads_and_means_what_it_says(tmp_path: Path) -> None:
    """F2: `kconfig: {path:}` (the key is `root`), `event_tags: {emits: produce}` (the roles are
    `producer` / `consumer`) and `doxyfile:` were documented and wrong. The block is loaded as
    written, so the reference cannot drift from the loader again.

    @brief OVERVIEW.md's `.clew.yaml` example loads through the real loader.
    """
    text = (REPO / "docs" / "OVERVIEW.md").read_text(encoding="utf-8")
    block = re.search(
        r"```yaml\n# a --declare document, or <repo>/\.clew\.yaml\n(.*?)```", text, re.S
    )
    assert block, "OVERVIEW.md's declaration example block was not found"
    (tmp_path / "doxygen").mkdir()
    (tmp_path / "doxygen" / "project.doxyfile").write_text("INPUT = .\n", encoding="utf-8")
    (tmp_path / ".clew.yaml").write_text(block.group(1), encoding="utf-8")
    decl = load_declaration(tmp_path)
    assert decl["kconfig"] == {"root": "Kconfig"}
    assert set((declared_event_tags(decl) or {}).values()) == {"producer", "consumer"}
