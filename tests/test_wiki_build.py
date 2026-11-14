# SPDX-License-Identifier: MIT
"""`clew wiki check` and `clew wiki build`: the `wiki:` section, validated and rendered.

1.4.0 Track 4, W5/W6 (owner 2026-11-13: Sphinx + MyST behind the `clew-trace[wiki]` extra; the
output a self-contained static site; `check` runs with no Sphinx import). The `wiki:` section of
`.clew.yaml` names the site's title, its prose, the flows to derive, the CI evidence, a source
link template and audiences. `check` refuses an unknown key by name and verifies everything the
section points at exists; `build` writes the site. An audience that excludes bodies gets a site
with no function bodies in it — redaction is a property of the build, asserted on the output.

@brief Tests for clew.wiki.config / check / build.
@version 1
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_PY = '''\
def load():
    """Load the data. REQ-W-001"""
    return parse("x")


def parse(raw):
    return raw  # SECRET_BODY_MARKER
'''

_WIKI = """\
wiki:
  title: Demo Wiki
  docs: [README.md]
  flows:
    - entry: load
      depth: 2
  links:
    template: "https://example.invalid/blob/{commit}/{file}#L{line}"
  audiences:
    partner:
      exclude_bodies: true
"""


## @brief A small Python repository with a `.clew.yaml` wiki section, indexed.
## @param tmp_path Scratch directory.
## @return (repo, index).
## @version 1
@pytest.fixture()
def site_repo(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Build the fixture. @return Paths."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "data.py").write_text(_PY)
    (repo / "README.md").write_text("# Demo\n\nThe demo repository.\n")
    (repo / ".clew.yaml").write_text(_WIKI)
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return repo, out


def test_the_build_still_accepts_a_wiki_section(site_repo: tuple[Path, Path]) -> None:
    """`wiki:` IS ANOTHER TOOL'S SECTION, like `guard:`: the build must not refuse the file.

    @brief Indexing a repo whose .clew.yaml has `wiki:` succeeds.
    @return None.
    @version 1
    """
    _repo, out = site_repo
    assert out.is_file()


def test_check_passes_a_valid_section_and_imports_no_sphinx(site_repo: tuple[Path, Path]) -> None:
    """@brief A valid section checks clean, with Sphinx never imported.
    @return None.
    @version 1
    """
    from clew.wiki.check import check_wiki

    for mod in [m for m in sys.modules if m == "sphinx" or m.startswith("sphinx.")]:
        sys.modules.pop(mod)
    repo, out = site_repo
    assert check_wiki(repo, out) == []
    assert "sphinx" not in sys.modules


def test_check_names_every_problem(site_repo: tuple[Path, Path]) -> None:
    """@brief Unknown key, missing flow entry, missing prose file — each named.
    @return None.
    @version 1
    """
    from clew.wiki.check import check_wiki

    repo, out = site_repo
    (repo / ".clew.yaml").write_text(
        _WIKI.replace("entry: load", "entry: no_such_fn").replace("README.md", "MISSING.md")
        + "  colour: blue\n"
    )
    problems = "\n".join(check_wiki(repo, out))
    assert "colour" in problems and "no_such_fn" in problems and "MISSING.md" in problems


def test_build_writes_a_self_contained_site(site_repo: tuple[Path, Path], tmp_path: Path) -> None:
    """NO CDN, NO RUNTIME FETCH: the generated HTML references nothing off the site.

    @brief The site has an index, a flow page with an inline SVG, and no remote assets.
    @return None.
    @version 1
    """
    from clew.wiki.build import build_wiki

    repo, out = site_repo
    site = build_wiki(repo, out, tmp_path / "site")
    pages = {p.name: p.read_text() for p in site.rglob("*.html")}
    assert "index.html" in pages and "Demo Wiki" in pages["index.html"]
    flow = next(text for name, text in pages.items() if name.startswith("flow-"))
    assert "<svg" in flow and "parse" in flow
    for text in pages.values():
        assert "https://cdn" not in text and 'src="http' not in text
    assert any("SECRET_BODY_MARKER" in t for t in pages.values()), "bodies render by default"


def test_an_audience_that_excludes_bodies_gets_none(
    site_repo: tuple[Path, Path], tmp_path: Path
) -> None:
    """REDACTION IS ASSERTED ON THE OUTPUT, not on a flag: no page of the partner site may contain
    a function body.

    @brief `--audience partner` with exclude_bodies renders no body text.
    @return None.
    @version 1
    """
    from clew.wiki.build import build_wiki

    repo, out = site_repo
    site = build_wiki(repo, out, tmp_path / "partner", audience="partner")
    for page in site.rglob("*.html"):
        assert "SECRET_BODY_MARKER" not in page.read_text(), page


def test_the_cli_check_exits_nonzero_on_a_problem(
    site_repo: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief `clew wiki check` exits 0 clean, 1 with each problem on its own line.
    @return None.
    @version 1
    """
    from clew.wiki.command import wiki_main

    repo, out = site_repo
    args = ["check", "--index", str(out), "--repo-root", str(repo)]
    assert wiki_main(args) == 0
    (repo / ".clew.yaml").write_text(_WIKI + "  colour: blue\n")
    assert wiki_main(args) == 1
    assert "colour" in capsys.readouterr().out
