# SPDX-License-Identifier: MIT
"""Vendor areas are separate boundary blocks sized by their use; owners overlay the map and file
pages, and an audience can redact them (P5, item 3; 2.0.0).

OWNER RULINGS (wiki round 5): "Vendor sits outside the system boundary, one node per vendored
area", and the owners layer (S2/S3, built in P2, served in P3) is drawn where a reader looks for
who to ask. An audience that publishes outside the team (`wiki.audiences.<name>`) can leave the
names out, as it can leave out bodies and requirement text.

- ONE BLOCK PER AREA: every nested git tree and every declared `vendored:` root is its own block,
  `Vendor: <root>`, marked `vendor`. They were all one `Vendor` block.
- SIZED BY USE: a vendor wedge's share of the circle is the calls into it from first-party code,
  not its function count, so a large library the project barely touches stays small.
- OWNERS: each map node carries its file's first owner, an `Owners` lens colours by it, and a file
  page lists the file's owners.

@brief Tests vendor areas, the owners overlay and its redaction.
@version 1
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_FILES = {
    ".github/CODEOWNERS": "* @core\n/src/net/ @net-team\n",
    "src/net/sock.c": "int lib_a(void);\nint sock_open(void) { return lib_a() + lib_a(); }\n",
    ## Two first-party functions call into a/ (sock_open and main), one into b/ (main). A call is
    ## counted per (caller, callee) function pair, so sock_open's two calls to lib_a are one.
    "src/main.c": "int sock_open(void);\nint lib_a(void);\nint lib_b(void);\n"
    "int main(void) { return sock_open() + lib_a() + lib_b(); }\n",
    "third_party/a/a.c": "int a_inner(void) { return 1; }\nint a_more(void) { return 2; }\nint lib_a(void) { return a_inner() + a_more(); }\n",
    "third_party/b/b.c": "int lib_b(void) { return 3; }\n",
    "README.md": "# Owned\n",
}
_DECL = """\
vendored: [third_party/a, third_party/b]
wiki:
  title: Owned
  docs: [README.md]
  audiences:
    public: {exclude_owners: true}
"""


def _site(root: Path, audience: str | None) -> dict[str, str]:
    """@brief Build the site. @return {page: html}."""
    from clew.wiki.build import build_wiki

    repo = root / "repo"
    if not repo.exists():
        for rel, text in _FILES.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text)
        (repo / ".clew.yaml").write_text(_DECL)
        _run_pipeline(
            _build_argparser().parse_args(
                ["--output", str(root / "clew.db"), "--repo-root", str(repo)]
            )
        )
    html = build_wiki(repo, root / "clew.db", root / f"out-{audience or 'all'}", audience=audience)
    return {p.relative_to(html).as_posix(): p.read_text() for p in html.glob("*.html")}


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief A scratch root. @return Path."""
    return tmp_path_factory.mktemp("owned")


def _web(page: str) -> dict:
    """@brief The map page's inline data. @return Data."""
    found = re.search(r'<script type="application/json" id="web-data">(.*?)</script>', page, re.S)
    assert found, "no web data on the map page"
    return json.loads(found.group(1).replace("<\\/", "</"))


def test_each_vendored_area_is_its_own_block_sized_by_calls_into_it(root: Path) -> None:
    """@brief Two vendor blocks; a's wedge (2 callers in) is wider than b's (1)."""
    blocks = {b["id"]: b for b in _web(_site(root, None)["map.html"])["blocks"]}
    a, b = blocks["Vendor: third_party/a"], blocks["Vendor: third_party/b"]
    assert a["vendor"] is True and b["vendor"] is True
    assert (a["calls_in"], b["calls_in"]) == (2, 1)
    assert (a["a1"] - a["a0"]) > (b["a1"] - b["a0"])


def test_owners_overlay_the_map_and_the_file_page(root: Path) -> None:
    """@brief Nodes carry their owner, the lens is offered, the file page lists owners."""
    pages = _site(root, None)
    web = _web(pages["map.html"])
    owners = {n["name"]: n.get("owner") for n in web["nodes"]}
    assert owners["sock_open"] == "@net-team" and owners["main"] == "@core"
    assert '<option value="owner">' in pages["map.html"]
    file_page = next(v for k, v in pages.items() if k.startswith("sym-src-net-sock-c"))
    assert "@net-team" in file_page


def test_an_audience_can_redact_owners(root: Path) -> None:
    """@brief exclude_owners: no owner on any node, no lens, no names on file pages."""
    pages = _site(root, "public")
    web = _web(pages["map.html"])
    assert all("owner" not in n for n in web["nodes"])
    assert '<option value="owner">' not in pages["map.html"]
    assert not any("@net-team" in v for v in pages.values())
