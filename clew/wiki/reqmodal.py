# SPDX-License-Identifier: MIT
"""One requirement's whole trace, in the site's shared modal (round 3, P1d).

Owner 2026-11-15: requirements front and centre; the acceptance drop-down in the table was noise;
"being able to click into a test associated with a requirement and see WHAT it's testing". The
requirement's id opens a modal holding everything it links to:

  * its title and acceptance criteria (both withheld under `exclude_requirement_text`);
  * its tier, and the catalog's declared status and priority;
  * the functions implementing it, linked to source;
  * its tests, each with its status and how it was linked (tag, measured, catalog, inferred) —
    a long list is cut, and the cut is SAID, never silent;
  * the flows its implementers are on, linked to their pages;
  * model entries and mutation outcomes, when it has any;
  * a prefilled "raise an issue" link, when the repository has a tracker.

@brief Render a requirement's modal.
@version 1
"""

from __future__ import annotations

from typing import Any

from .config import Audience
from .htmltable import code, md_title, source_url, tag, text
from .issues import Target, issue_url
from .modal import modal

## The most tests a modal lists before saying how many it left out.
_MAX_TESTS = 40


## @brief The requirement's cell: its id opening its modal, and its title under it.
## @param row The evidence row.
## @param entry Its catalog entry ({} when undeclared).
## @param ctx The page context: trace, rules, flows, issue target.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-022
def requirement_cell(row: Any, entry: dict, ctx: dict[str, Any]) -> str:
    """@brief Id, title and modal. @return HTML."""
    rules: Audience = ctx["rules"]
    title = (
        "" if rules.exclude_requirement_text else (row.title or str(first(entry, "name", "title")))
    )
    heading = f"{row.req_id} — {title}" if title else row.req_id
    cell = (
        f'<span class="rid" id="{text(row.req_id)}">'
        + modal("req-" + _key(row.req_id), row.req_id, heading, _body(row, entry, title, ctx))
        + "</span>"
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
## @version 3
## @dg_internal
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
        (_tests_heading(row.tests), _tests(row, trace.test_href), "ul"),
        ("Flows through it", _flows(row, ctx["flows"]), "ul"),
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
## @dg_internal
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
## @dg_internal
def _items(items: Any) -> str:
    """@brief Wrap items. @return HTML."""
    return "".join(f"<li>{i}</li>" for i in items)


## @brief "Tests (N)".
## @param tests (test, status) pairs.
## @return The heading.
## @version 1
## @dg_internal
def _tests_heading(tests: tuple) -> str:
    """@brief Heading. @return Text."""
    return f"Tests ({len(tests)})"


## @brief The tests, each with its status and link kind; a long list is cut and the cut said.
## @param row The evidence row.
## @param hrefs {test name: its section}.
## @return HTML.
## v2: each test links to its section — what it tests (round 3, P2a).
## @version 2
## @dg_internal
def _tests(row: Any, hrefs: dict[str, str]) -> str:
    """@brief Test items. @return HTML."""
    items = [f"{test_link(t, hrefs)} {tag(s)}{via(row, t)}" for t, s in row.tests[:_MAX_TESTS]]
    if len(row.tests) > _MAX_TESTS:
        items.append(
            f'<span class="none">and {len(row.tests) - _MAX_TESTS} more, not listed</span>'
        )
    return _items(items)


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
## @dg_internal
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
## @dg_internal
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
## @dg_internal
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
