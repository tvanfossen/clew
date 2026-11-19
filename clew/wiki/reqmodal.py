# SPDX-License-Identifier: MIT
"""One requirement's whole trace, on its own page (round 3, P1d; round 4, R4).

Owner 2026-11-15: requirements front and centre; the acceptance drop-down in the table was noise;
"being able to click into a test associated with a requirement and see WHAT it's testing". The
requirement's id opens ITS OWN PAGE (round 4, R4 — owner 2026-11-16: "individual links that are
self contained", not one giant scrolling page; the modal it replaces cut long test lists) holding
everything it links to:

  * its title and acceptance criteria (both withheld under `exclude_requirement_text`);
  * its tier, and the catalog's declared status and priority;
  * the functions implementing it, linked to source;
  * its tests, every one, in two tables — linked directly (tag, mapping, catalog, measured) and
    reached through calls (inferred) — each with its result, how it was linked, and its EXTENT:
    which of the requirement's implementers it executes or reaches ("covers 2 of 9");
  * the flows its implementers are on, linked to their pages;
  * model entries and mutation outcomes, when it has any;
  * a prefilled "raise an issue" link, when the repository has a tracker.

@brief Render a requirement's page.
@version 2
"""

from __future__ import annotations

from typing import Any

from .config import Audience
from .htmltable import code, md_title, source_url, tag, text
from .issues import Target, issue_url


## @brief The requirement's cell: its id linking to its page, and its title under it.
## @param row The evidence row.
## @param entry Its catalog entry ({} when undeclared).
## @param ctx The page context: trace, rules, flows, issue target.
## @return HTML.
## v2 (round 4, R4): links to the requirement's page instead of opening a modal.
## @version 2
## @req REQ-DDB-WIKI-022
def requirement_cell(row: Any, entry: dict, ctx: dict[str, Any]) -> str:
    """@brief Id, title and modal. @return HTML."""
    rules: Audience = ctx["rules"]
    title = (
        "" if rules.exclude_requirement_text else (row.title or str(first(entry, "name", "title")))
    )
    cell = (
        f'<span class="rid" id="{text(row.req_id)}">'
        f'<a href="{text(page_of(row.req_id))}.html">{text(row.req_id)}</a></span>'
    )
    if title:
        cell += f'<div class="rtitle">{text(title)}</div>'
    return cell


## @brief The modal body.
## @param row The evidence row.
## @param entry Its catalog entry.
## @param title Its title, or "" when withheld.
## @param ctx The page context.
## @return HTML.
## v2: each implementer shows its file and line beside its symbol link (P1f).
## v3: tests link to their sections.
## v4: open issues (P3a).
## v5: decisions naming the requirement (P3c).
## v6 (round 4, R4): the body of the requirement's own page; every test, as tables with extent.
## @version 6
## @utility
def _body(row: Any, entry: dict, title: str, ctx: dict[str, Any]) -> str:
    """@brief Assemble sections. @return HTML."""
    rules: Audience = ctx["rules"]
    trace = ctx["trace"]
    criteria = (
        ""
        if rules.exclude_requirement_text
        else str(first(entry, "acceptance_criteria", "acceptance", "description"))
    )
    facts = [("tier", tag(row.tier))]
    for label, keys in (
        ("declared", ("x-status", "status")),
        ("priority", ("x-priority", "priority")),
    ):
        value = first(entry, *keys)
        if value:
            facts.append((label, text(str(value))))
    sections = [
        ("", "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts), "dl"),
        ("Acceptance", f"<p>{md_title(criteria)}</p>" if criteria else "", ""),
        (
            "Implemented by",
            _items(
                f'{trace.link(n, f, ln)} <span class="ver">{text(f)}:{ln}</span>'
                for n, f, ln in row.implementer_sites
            ),
            "ul",
        ),
        (_tests_heading(row.tests), _tests(row, trace.test_href), ""),
        ("Flows through it", _flows(row, ctx["flows"]), "ul"),
        ("Open issues", issue_links((trace.issues or {}).get(row.req_id, []), True), ""),
        (
            "Decisions",
            _items(
                f'<a href="{text(d.href)}">{text(d.title)}</a> <span class="ver">{text(d.status)}</span>'
                for d in trace.decisions.get(row.req_id, [])
            ),
            "ul",
        ),
        ("Model entries", _items(code(n) for n in trace.nodes_for(row.req_id)), "ul"),
        (
            "Mutations",
            _items(f"{code(m)} → {code(t)} {text(o)}" for m, t, o in row.mutations or ()),
            "ul",
        ),
    ]
    html = "".join(_section(h, body, kind) for h, body, kind in sections if body)
    return html + _issue_link(row, title, criteria, ctx)


## @brief One modal section.
## @param heading The heading, or "" for none.
## @param body Its content.
## @param kind "ul", "dl" or "" (already wrapped).
## @return HTML.
## @version 1
## @utility
def _section(heading: str, body: str, kind: str) -> str:
    """@brief Wrap a section. @return HTML."""
    head = f"<h4>{heading}</h4>" if heading else ""
    if kind == "ul":
        return f'{head}<ul class="modal-list">{body}</ul>'
    if kind == "dl":
        return f'{head}<dl class="kv">{body}</dl>'
    return head + body


## @brief List items.
## @param items Item HTML.
## @return HTML.
## @version 1
## @utility
def _items(items: Any) -> str:
    """@brief Wrap items. @return HTML."""
    return "".join(f"<li>{i}</li>" for i in items)


## @brief "Tests (N)".
## @param tests (test, status) pairs.
## @return The heading.
## @version 1
## @utility
def _tests_heading(tests: tuple) -> str:
    """@brief Heading. @return Text."""
    return f"Tests ({len(tests)})"


## @brief Every test of a requirement, as two tables: linked directly, and reached through calls.
## @param row The evidence row.
## @param hrefs {test name: its section}.
## @return HTML.
## v3 (round 4, R4/R5): tables, every test, each with its extent; nothing cut.
## @version 3
## @utility
def _tests(row: Any, hrefs: dict[str, str]) -> str:
    """A TEST'S EXTENT IS SAID (owner 2026-11-17: "a test could cover sections of multiple
    requirements, or one requirement in full"): which of the requirement's implementers it executed
    (measured) or reaches (inferred) — "2 of 9" never reads like "9 of 9". A failing test sorts
    first; then the NEAREST (fewest calls between test and implementer — the test aimed at this
    code, not one that passes through it on the way elsewhere); then the widest extent.

    @brief Test tables.
    @return HTML.
    """
    reach = dict(row.extent or ())
    hops = dict(row.distance)
    total = len(row.implementers)
    order = {"failed": 0, "error": 0, "skipped": 1, "absent": 2, "passed": 3}

    def key(item: tuple[str, str]) -> tuple:
        return (
            order.get(item[1], 2),
            hops.get(item[0], 0),
            -len(reach.get(item[0], ())),
            item[0],
        )

    direct = sorted((t for t in row.tests if t[0] not in row.inferred_tests), key=key)
    reached = sorted((t for t in row.tests if t[0] in row.inferred_tests), key=key)
    out = ""
    for heading, rows in (("Linked directly", direct), ("Reached through calls", reached)):
        if not rows:
            continue
        body = "".join(
            f"<tr><td>{test_link(t, hrefs)}</td><td>{tag(st)}</td><td>{_kind(row, t)}</td>"
            f"<td>{_extent(reach.get(t), total)}</td>"
            f'<td class="n">{hops.get(t, "—")}</td></tr>'
            for t, st in rows
        )
        out += (
            f"<h5>{heading} ({len(rows)})</h5>"
            '<table class="clew req-tests"><thead><tr><th>test</th><th>result</th>'
            "<th>linked by</th><th>implementers exercised</th>"
            '<th class="n" title="the fewest calls between the test and an implementer">calls away'
            "</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )
    return out


## @brief How a test was linked, as a word.
## @param row The evidence row.
## @param test The test.
## @return HTML.
## @version 1
## @utility
def _kind(row: Any, test: str) -> str:
    """@brief Link kind. @return HTML."""
    return via(row, test).strip() or '<span class="via via-tag">tag</span>'


## @brief "k of n", naming the implementers when few.
## @param names The implementers the test exercised, or None when unknown.
## @param total The requirement's implementer count.
## @return HTML.
## @version 1
## @utility
def _extent(names: tuple[str, ...] | None, total: int) -> str:
    """@brief Extent cell. @return HTML."""
    if names is None:
        return '<span class="none">unknown</span>'
    head = f"{len(names)} of {total}"
    if not names or len(names) > 4:
        return text(head)
    return f"{text(head)}: " + ", ".join(code(n) for n in names)


## @brief The page name of a requirement.
## @param req_id The id.
## @return The page name (without .html).
## @version 1
## @req REQ-DDB-WIKI-022
def page_of(req_id: str) -> str:
    """@brief Page name. @return Name."""
    return "req-" + _key(req_id)


## @brief The evidence diagram for a requirement page, and its map overlay link.
## @param row The evidence row.
## @return HTML lines, or none when the requirement has neither implementer nor test.
## v2 (2.0.0, P5.4): "Show on the map" opens the requirement overlay.
## @version 2
## @req REQ-DDB-WIKI-022
def _evidence_line(row: Any) -> list[str]:
    """@brief The diagram in a scrolling figure. @return Lines."""
    from urllib.parse import quote

    from .reqdiagram import evidence_svg

    svg = evidence_svg(row)
    lines = [f'<figure class="req-evidence-fig">{svg}</figure>'] if svg else []
    ## THE OVERLAY (P5.4): only with implementers, so the link never opens an empty map.
    if row.implementers:
        lines.append(
            f'<p class="req-map"><a href="map.html#req={quote(row.req_id, safe="")}">'
            "Show on the map</a></p>"
        )
    return lines


## @brief The EARS badge line for a requirement page, when `wiki.check.ears` is on.
## @param row The evidence row.
## @param entry Its catalogue entry.
## @param ctx The page context (`ears`).
## @return One HTML line, or none.
## @version 1
## @req REQ-DDB-WIKI-042
def _ears_line(row: Any, entry: dict, ctx: dict[str, Any]) -> list[str]:
    """@brief Badge on the statement the catalogue gives, else the title. @return Lines."""
    if not ctx.get("ears"):
        return []
    from ..requirements import catalog_value
    from .ears import ears_badge, statement_of

    statement = statement_of(catalog_value(entry, "acceptance"), row.title)
    return [f'<p class="ears-line">{ears_badge(statement)}</p>']


## @brief Write one page per requirement.
## @param trace The gathered trace.
## @param ctx The page context: trace, rules, flows, issue target.
## @param source The Sphinx source directory.
## @return The page names written.
## v2: EARS badge and check notes (2.0.0, S9)
## v3: evidence diagram (2.0.0, P5.4)
## @version 3
## @req REQ-DDB-WIKI-022
def requirement_pages(trace: Any, ctx: dict[str, Any], source: Any) -> list[str]:
    """ORPHAN PAGES (linked from the index, not from the toctree), one per requirement, so a
    requirement is a URL a reader can share and the index stays a table.

    @brief Write req-*.md.
    @return Names.
    """
    from pathlib import Path

    rules: Audience = ctx["rules"]
    names = []
    for row in trace.evidence:
        entry = trace.declared.get(row.req_id, {})
        title = (
            ""
            if rules.exclude_requirement_text
            else (row.title or str(first(entry, "name", "title")))
        )
        name = page_of(row.req_id)
        heading = f"{row.req_id}: {title}" if title else row.req_id
        lines = [
            "---",
            "orphan: true",
            "---",
            "",
            f"# {md_title(heading)}",
            "",
            "```{raw} html",
            '<p class="crumbs"><a href="requirements.html">← Requirements</a></p>',
            *_ears_line(row, entry, ctx),
            *_evidence_line(row),
            f'<div class="req-page">{_body(row, entry, title, ctx)}</div>',
            "```",
            "",
        ]
        (Path(source) / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")
        names.append(name)
    return names


## @brief Open issues as links: inline (`#12, #13`) or as a list with titles.
## @param issues The issues.
## @param titled A list with titles, rather than inline numbers.
## @return HTML ("" for none).
## @version 1
## @req REQ-DDB-WIKI-028
def issue_links(issues: list, titled: bool = False) -> str:
    """@brief Issue links. @return HTML."""
    if not issues:
        return ""
    if not titled:
        return ", ".join(f'<a href="{text(i.url)}">#{text(i.id)}</a>' for i in issues)
    items = "".join(
        f'<li><a href="{text(i.url)}">#{text(i.id)}</a> {text(i.title)}</li>' for i in issues
    )
    return f'<ul class="modal-list">{items}</ul>'


## @brief A test's name, linked to its section when it has one.
## @param name The test.
## @param hrefs {test name: its section}.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-026
def test_link(name: str, hrefs: dict[str, str]) -> str:
    """@brief Link a test. @return HTML."""
    href = hrefs.get(name)
    return f'<a href="{text(href)}">{code(name)}</a>' if href else code(name)


## @brief How a test was linked, when weaker than a tag.
## @param row The evidence row.
## @param test The test.
## @return HTML ("" for a tagged link).
## @version 1
## @req REQ-DDB-WIKI-022
def via(row: Any, test: str) -> str:
    """@brief Link kind. @return HTML."""
    for kind, tests in (
        ("measured", row.measured_tests),
        ("catalog", row.declared_tests),
        ("inferred", row.inferred_tests),
    ):
        if test in tests:
            return f' <span class="via via-{kind}" title="linked by {kind}">{kind}</span>'
    return ""


## @brief The flows an implementer of the requirement is on.
## @param row The evidence row.
## @param flows The flow pages.
## @return HTML.
## @version 1
## @utility
def _flows(row: Any, flows: list) -> str:
    """BY FUNCTION AND FILE, not by file alone: a file holding many functions does not put every
    requirement in it on every flow that touches the file.

    @brief Flow items.
    @return HTML.
    """
    implementers = {(n, f) for n, f, _l in row.implementer_sites}
    return _items(
        f'<a href="{text(p.name)}.html">{md_title(p.title)}</a>'
        for p in sorted(flows, key=lambda p: p.title)
        if implementers & p.functions
    )


## @brief The prefilled issue link, or "" without a tracker.
## @param row The evidence row.
## @param title Its title ("" when withheld).
## @param criteria Its acceptance text ("" when withheld).
## @param ctx The page context.
## @return HTML.
## @version 1
## @utility
def _issue_link(row: Any, title: str, criteria: str, ctx: dict[str, Any]) -> str:
    """THE AUDIENCE RULE HOLDS IN THE URL TOO: withheld text never rides in the issue's body.

    @brief Issue link.
    @return HTML.
    """
    target: Target | None = ctx["issues"]
    if target is None:
        return ""
    trace = ctx["trace"]
    lines = [criteria] if criteria else []
    for name, rel, line in row.implementer_sites[:10]:
        url = source_url(trace.template, trace.commit, rel, max(line, 1))
        lines.append(f"- `{name}` {rel}:{line}" + (f" {url}" if url else ""))
    url = issue_url(target, row.req_id, title or row.req_id, "\n".join(lines))
    label = "GitHub" if target[0] == "github" else "Azure DevOps"
    return f'<p class="issue-link"><a href="{text(url)}" rel="noopener">Raise an issue on {label}</a></p>'


## @brief A requirement id as a modal key.
## @param req_id The id.
## @return The key.
## @version 1
## @utility
def _key(req_id: str) -> str:
    """@brief Keep the characters a URL fragment carries. @return Key."""
    import re

    return re.sub(r"[^\w.:-]", "_", req_id)


## @brief The first of several keys a catalog entry carries.
## @param entry The entry.
## @param keys Candidate keys, in order.
## @return The value, or "".
## @version 1
## @req REQ-DDB-WIKI-022
def first(entry: dict, *keys: str) -> Any:
    """@brief Look up. @return Value."""
    for key in keys:
        if entry.get(key):
            return entry[key]
    return ""
