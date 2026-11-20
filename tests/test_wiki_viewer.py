# SPDX-License-Identifier: MIT
"""Viewer caps that expand without bloating the page (V1–V6; owner Q/A 2026-11-20).

The config review found six display caps that hid content with no way to see it. Owner Q/A
2026-11-20 chose a WEIGHT-AWARE mix, because whatever an expander hides still ships in every page
(the 14.6 MB evidence-diagram lesson):

| # | cap | now |
|---|---|---|
| V1 | 3 slices drawn on a test page | the rest are listed as links (already so) |
| V2 | 2 context steps | each slice heading links its flow page, lit for the test (already so) |
| V3 | 12 neighbours | a `<details>` "N more" with the full name list |
| V4 | 12 requirement chains drawn | the requirement table below lists every one (already so) |
| V5 | 5 flows per changed function | a `<details>` "N more" with the full list |
| V6 | 120 body lines | `wiki.body_lines`, and a cut body links its full source |

@brief Tests the viewer caps.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace


def test_neighbours_past_the_cap_open_in_a_details() -> None:
    """@brief V3: 15 callers — 12 inline, 3 behind "3 more", every name present."""
    from clew.wiki.symbols import _names

    pairs = [(f"f{i}", "a.py") for i in range(15)]
    html = _names(pairs, {("f0", "a.py")})
    assert "<summary>3 more</summary>" in html
    assert all(f">f{i}<" in html for i in range(15))


def test_flows_past_the_cap_open_in_a_details() -> None:
    """@brief V5: 7 flows on a changed function's row — 5 shown, 2 behind "2 more", all linked."""
    from clew.wiki.impactpage import _flow_cell

    pages = [SimpleNamespace(name=f"flow-{i}", title=f"Flow {i}", role="product") for i in range(7)]
    html = _flow_cell(pages)
    assert "<summary>2 more</summary>" in html
    assert all(f'href="flow-{i}.html"' in html for i in range(7))


def test_body_lines_is_a_setting_and_a_cut_body_links_its_source(tmp_path) -> None:
    """@brief V6: `wiki.body_lines` (default 120); past it, "N more lines" links the full source."""
    from clew.wiki.config import load_wiki_config
    from clew.wiki.symbols import Definition, _body

    (tmp_path / ".clew.yaml").write_text("wiki:\n  body_lines: 3\n")
    config, problems = load_wiki_config(tmp_path, None)
    assert config.body_lines == 3 and problems == []
    (tmp_path / "m.py").write_text("def f():\n" + "".join(f"    x{i} = {i}\n" for i in range(10)))
    d = Definition(1, "f", "m.py", "def f()", "", 1, 11)
    ctx = {"body_lines": 3, "template": "https://example.invalid/{file}#L{line}", "commit": "c0"}
    html = _body(tmp_path, d, ctx)
    assert "8 more lines" in html and 'href="https://example.invalid/m.py#L1"' in html
