# SPDX-License-Identifier: MIT
"""Change impact, as its own section of the site (round 3, P1g).

Owner 2026-11-15: "change impact can be a top bar item". clew-guard's impact report
(`impact.json`) names the requirements whose implementing functions changed. The section follows
each CHANGED FUNCTION to the requirements it implements and the flows it is on, and points at the
map's change lens, where the same functions are lit.

ABSENCE IS NOT EMPTINESS: with no report the section says the change was NOT MEASURED and how to
measure it; an empty report is a measured zero — no requirement was affected.

@brief Write the change-impact page.
@version 1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Audience
from .htmltable import code, md_title, table, text

_LEAD = (
    "What the last change touched, from clew-guard's impact report: each changed function, the "
    "requirements it implements, and the flows it is on."
)
_NOT_MEASURED = (
    '<p class="not-measured"><b>Not measured.</b> No impact report was found. clew-guard writes '
    "one (<code>impact/impact.json</code> under its output directory) when it checks a change; point "
    "<code>wiki.impact</code> at it to fill this page.</p>"
)


## @brief Write the change-impact page.
## @param trace The gathered trace (impact, link template).
## @param pages The flow pages.
## @param rules The audience rules.
## @param source The Sphinx source directory.
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-024
def impact_page(trace: Any, pages: list, rules: Audience, source: Path) -> str:
    """@brief Write impact.md. @return Page name."""
    lines = [
        "# Change impact",
        "",
        _LEAD,
        "",
        "```{raw} html",
        _body(trace, pages, rules),
        "```",
        "",
    ]
    (Path(source) / "impact.md").write_text("\n".join(lines), encoding="utf-8")
    return "impact"


## @brief The page body for a report that is absent, empty, or has entries.
## @param trace The gathered trace.
## @param pages The flow pages.
## @param rules The audience rules.
## @return HTML.
## @version 1
## @dg_internal
def _body(trace: Any, pages: list, rules: Audience) -> str:
    """@brief Body. @return HTML."""
    if trace.impact is None:
        return _NOT_MEASURED
    if not trace.impact:
        return '<p class="measured-zero">No requirement was affected by the last change.</p>'
    changed = _changed(trace.impact)
    flows = {fn: _flows_of(fn, pages) for fn in changed}
    touched = {p.name for names in flows.values() for p in names}
    stats = (
        (
            "requirements",
            len({r for reqs in changed.values() for r in reqs}),
            "requirements affected",
        ),
        ("functions", len(changed), "functions changed"),
        ("flows", len(touched), "flows touched"),
    )
    cards = "".join(
        f'<div class="stat" data-stat="{k}"><b>{n}</b><span>{label}</span></div>'
        for k, n, label in stats
    )
    rows = [
        [
            f'{trace.link(name, rel, 0)}<div class="ver">{text(rel)}</div>',
            " ".join(
                f'<a class="req-badge" href="requirements.html#{text(r)}">{text(r)}</a>'
                for r in sorted(reqs)
            ),
            "<br>".join(
                f'<a href="{text(p.name)}.html">{md_title(p.title)}</a>' for p in flows[(name, rel)]
            ),
        ]
        for (name, rel), reqs in sorted(changed.items())
    ]
    lens = '<p><a href="map.html#lens=change">See the changed functions on the map</a></p>'
    by_req = _by_requirement(trace, rules)
    return (
        f'<div class="stats">{cards}</div>{lens}'
        + table(["function changed", "requirements", "flows"], rows, keep=("function changed",))
        + "<h2>By requirement</h2>"
        + by_req
    )


## @brief Changed functions and the requirements each was reported under.
## @param impact The report's entries.
## @return {(function, file): {requirement ids}}.
## @version 1
## @dg_internal
def _changed(impact: list[dict]) -> dict[tuple[str, str], set[str]]:
    """@brief Invert the report. @return Map."""
    out: dict[tuple[str, str], set[str]] = {}
    for entry in impact:
        for fn in entry.get("functions") or []:
            key = (str(fn.get("name") or ""), str(fn.get("file") or ""))
            out.setdefault(key, set()).add(str(entry.get("req_id") or ""))
    return out


## @brief The flows a function is on.
## @param fn (function, file).
## @param pages The flow pages.
## @return Flow pages, by title.
## @version 1
## @dg_internal
def _flows_of(fn: tuple[str, str], pages: list) -> list:
    """@brief Flows through a function. @return Pages."""
    return sorted((p for p in pages if fn in p.functions), key=lambda p: p.title)


## @brief The report as written: one row per requirement with its changed functions.
## @param trace The gathered trace.
## @param rules The audience rules (no requirement names when text is excluded).
## @return HTML.
## @version 1
## @dg_internal
def _by_requirement(trace: Any, rules: Audience) -> str:
    """@brief Per-requirement table. @return HTML."""
    rows = [
        [
            f'<a href="requirements.html#{text(str(e.get("req_id")))}">{text(str(e.get("req_id")))}</a>',
            "" if rules.exclude_requirement_text else text(str(e.get("req_name") or "")),
            "<br>".join(
                f"{code(str(f.get('name')))} "
                f'<span class="ver">v{text(str(f.get("version") or "?"))}</span>'
                for f in e.get("functions") or []
            ),
        ]
        for e in trace.impact
    ]
    return table(["requirement", "name", "functions changed"], rows)
