# SPDX-License-Identifier: MIT
"""Success and info palette tokens; no colour outside a token (#73 item 4, 2.1).

#73 (an adopter, 2026-11-23): `wiki.theme.palette` had no success or info token, so "passed" was
drawn in `accent` and a palette could not give success its own colour (or keep accent for links);
and colours were written as literals outside `:root`, beyond a palette's reach.

@brief Tests the theme tokens.
@version 1
"""

from __future__ import annotations

import re
from pathlib import Path

import clew.wiki

_STATIC = Path(clew.wiki.__file__).parent / "themes" / "clew" / "static"


def _css() -> str:
    return (_STATIC / "clew.css").read_text()


def test_the_palette_takes_success_and_info(tmp_path: Path) -> None:
    """@brief Four new words, mapped to CSS tokens, accepted without a problem."""
    from clew.wiki.config import PALETTE, load_wiki_config

    assert {PALETTE[w] for w in ("success", "success_bg", "info", "info_bg")} == {
        "ok",
        "okbg",
        "info",
        "infobg",
    }
    (tmp_path / ".clew.yaml").write_text(
        "wiki:\n  theme:\n    palette: {success: '#1a7f37', info: '#0969da'}\n"
    )
    config, problems = load_wiki_config(tmp_path)
    assert not problems, problems


def test_every_token_is_defined_for_light_and_dark() -> None:
    """@brief `--ok`, `--okbg`, `--info`, `--infobg` in the light `:root` and the dark one."""
    css = _css()
    light = css[css.index(":root{") : css.index("}", css.index(":root{"))]
    dark_at = css.index("@media (prefers-color-scheme:dark)")
    dark = css[dark_at : css.index("}}", dark_at)]
    for token in ("--ok:", "--okbg:", "--info:", "--infobg:"):
        assert token in light and token in dark, token


def test_passed_is_drawn_in_success_not_accent() -> None:
    """@brief The passed states read `--ok`; the map's PASS too."""
    css = _css()
    for rule in (
        ".c-PASS,.c-passed{--c:var(--ok)}",
        ".ck.passed .mk{color:var(--ok)}",
        ".result-banner.r-passed{border-left-color:var(--ok)}",
    ):
        assert rule in css, rule
    web = (_STATIC / "web.js").read_text()
    assert (
        'PASS:"--ok"' in web and '"--ok"' in web.split("function colors()", 1)[1].split("]", 1)[0]
    )


def test_no_colour_literal_sits_outside_a_token_block() -> None:
    """@brief Every hex colour in the stylesheet is a token's value (inside a `:root{…}` block)."""
    css = _css()
    outside = re.sub(r":root(?::not\(\[[^\]]*\]\))?\{[^}]*\}", "", css)
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", outside) == []
