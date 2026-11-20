# SPDX-License-Identifier: MIT
"""The wiki's inline icon set (round 3, P1b): small line icons drawn in `currentColor`.

Inline so the site stays self-contained and an icon takes the colour of the text around it in
both schemes. Decorative only — every icon is `aria-hidden`, and the label beside it carries the
meaning.

@brief Inline SVG icons.
@version 2
"""

from __future__ import annotations

## Path data on a 24-unit grid, stroked.
_PATHS = {
    "requirements": "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
    "flows": "M5 3v18M19 3v18M5 8h14M15 5l4 3-4 3M19 15H5M9 12l-4 3 4 3",
    "impact": "M12 3v4M12 17v4M3 12h4M17 12h4M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
    "map": "M3 4h7v6H3zM14 4h7v6h-7zM8 15h8v6H8zM6.5 10v2.5h11V10M12 12.5V15",
    ## 2.0.0 (P5.6): nested boxes — C4's zoom from system to container to component.
    "architecture": "M3 3h18v18H3zM7 7h10v10H7zM10 10h4v4h-4z",
    ## #70 (P5.8): a stacked parcel — the components a package carries.
    "sbom": "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12L4 7.5M12 12v9",
    "docs": "M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h7",
    "nodes": "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5",
    ## GH #68: the product trace — a root with two branches down to dependency requirements.
    "product": "M9 3h6v4H9zM3 17h6v4H3zM15 17h6v4h-6zM12 7v5M6 17v-5h12v5",
    "test": "M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3",
    ## Owner Q/A 2026-11-20: the Tests tab — the same flask.
    "tests": "M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3",
    "issue": "M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 7v6M12 16v1",
    "close": "M6 6l12 12M18 6L6 18",
    "menu": "M4 7h16M4 12h16M4 17h16",
}


## @brief One icon as inline SVG.
## @param name An icon name (`_PATHS`).
## @param size Width and height in CSS pixels.
## @return SVG markup.
## @version 1
## @req REQ-DDB-WIKI-020
def icon(name: str, size: int = 20) -> str:
    """A NAME NOT IN THE SET RAISES KeyError: a page that asks for an icon that does not exist is
    a build fault, not a blank square.

    @brief Draw an icon.
    @return SVG.
    """
    path = _PATHS[name]
    return (
        f'<svg class="ico" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true"><path d="{path}"/></svg>'
    )
