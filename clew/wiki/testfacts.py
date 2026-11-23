# SPDX-License-Identifier: MIT
"""What a test tests (round 3, P2a).

Owner 2026-11-15: "being able to click into a test associated with a requirement and see WHAT
it's testing", and "when we display gherkin, please display it properly". A test is a function,
so it already has a section on its file's symbol page (`symbols`); this module supplies what
that section adds for a test:

  * its ASSERTIONS, read from its body per framework — Python `assert`, Catch2 / doctest
    `REQUIRE` / `CHECK` (and their `_FALSE`, `_THAT`, `_THROWS…` forms), GoogleTest `EXPECT_…` /
    `ASSERT_…`, Unity `TEST_ASSERT…` — a statement spanning lines read whole;
  * the requirements it VERIFIES, each with how it was linked (tag, measured, catalog,
    inferred) — the call path from the test to the implementer is drawn by `symbols`;
  * its RESULT, and mutation outcomes naming it.

A Gherkin SCENARIO is not a function: it gets a section on its feature file's page, rendered as
Gherkin — Feature / Rule / Scenario headings, keyword-highlighted steps, tags as chips, Examples
tables as tables, doc strings as blocks.

@brief Test facts, assertion reading and Gherkin rendering.
@version 1
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

## A line that opens an assertion statement.
_ASSERT = re.compile(
    r"^\s*(assert\b|(?:REQUIRE|CHECK)(?:_\w+)?\s*\(|(?:EXPECT|ASSERT)_\w+\s*\(|TEST_ASSERT\w*\s*\()"
)
## The most lines one assertion statement is read across.
_MAX_SPAN = 8
_KEYWORDS = ("Given", "When", "Then", "And", "But", "*")
_BLOCK = re.compile(
    r"^(Feature|Rule|Background|Scenario Outline|Scenario Template|Scenario|Example|Examples|Scenarios)\s*:(.*)$"
)


## @brief What the site knows about one test.
## @version 1
@dataclass
class TestFacts:
    """@brief Status, verified requirements (id, link kind), mutation outcomes. @version 1"""

    status: str = "absent"
    verifies: list[tuple[str, str]] = field(default_factory=list)
    mutations: list[tuple[str, str]] = field(default_factory=list)


## @brief Invert the evidence: each test's status, requirements and mutation outcomes.
## @param evidence Requirement evidence rows.
## @return {test name: facts}.
## @version 1
## @req REQ-DDB-WIKI-026
def gather(evidence: list) -> dict[str, TestFacts]:
    """@brief Facts per test. @return Map."""
    out: dict[str, TestFacts] = {}
    for row in evidence:
        for test, status in row.tests:
            facts = out.setdefault(test, TestFacts(status=status))
            facts.verifies.append((row.req_id, link_kind(row, test)))
        for mechanism, test, outcome in row.mutations or ():
            out.setdefault(test, TestFacts()).mutations.append((mechanism, outcome))
    return out


## @brief How a test was linked to a requirement.
## @param row The evidence row.
## @param test The test.
## @return `measured`, `catalog`, `inferred` or `tag`.
## @version 1
## @utility
def link_kind(row: Any, test: str) -> str:
    """@brief Link kind. @return Kind."""
    for kind, tests in (
        ("measured", row.measured_tests),
        ("catalog", row.declared_tests),
        ("inferred", row.inferred_tests),
    ):
        if test in tests:
            return kind
    return "tag"


## @brief The assertion statements in a body, per framework, each read whole.
## @param lines The body's lines.
## @return Statements, whitespace collapsed.
## @version 1
## @req REQ-DDB-WIKI-026
def assertions(lines: list[str]) -> list[str]:
    """A STATEMENT OPEN AT ITS LINE'S END continues: lines are joined while parentheses are
    unbalanced, at most `_MAX_SPAN` lines — never into the next statement.

    @brief Read assertions.
    @return Statements.
    """
    out, i = [], 0
    while i < len(lines):
        if not _ASSERT.match(lines[i]):
            i += 1
            continue
        parts, depth, j = [], 0, i
        while j < len(lines) and j < i + _MAX_SPAN:
            parts.append(lines[j].strip())
            depth += lines[j].count("(") - lines[j].count(")")
            j += 1
            if depth <= 0:
                break
        out.append(" ".join(" ".join(parts).replace("( ", "(").split()))
        i = j
    return out


## @brief One scenario of a feature file, rendered as Gherkin with its Feature and Rule.
## @param text The feature file.
## @param line The scenario's line (1-based).
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-026
def render_scenario(text: str, line: int) -> str:
    """THE SCENARIO IN ITS CONTEXT: the Feature line and the Rule it sits under head it, with
    their tags; the scenario runs until the next block at its level.

    @brief Render Gherkin.
    @return HTML.
    """
    lines = text.splitlines()
    head = _context(lines, line - 1)
    body = []
    for raw in lines[line - 1 :][: _scenario_end(lines, line - 1)]:
        body.append(raw)
    return f'<div class="gherkin">{_render(head + body)}</div>'


## @brief The Feature and Rule lines (with their tags) above a scenario.
## @param lines The file's lines.
## @param at The scenario's index.
## @return Lines.
## @version 1
## @utility
def _context(lines: list[str], at: int) -> list[str]:
    """@brief Heading lines. @return Lines."""
    keep: list[str] = []
    for i in range(at):
        match = _BLOCK.match(lines[i].strip())
        if match and match.group(1) in ("Feature", "Rule"):
            if match.group(1) == "Feature":
                keep = []
            keep = [k for k in keep if not _is_rule(k)] if match.group(1) == "Rule" else keep
            keep += _tags_above(lines, i) + [lines[i]]
    tags = _tags_above(lines, at)
    return keep + tags


## @brief Whether a line opens a Rule.
## @param line The line.
## @return True for a Rule.
## @version 1
## @utility
def _is_rule(line: str) -> bool:
    """@brief Rule? @return Bool."""
    return line.strip().startswith("Rule:")


## @brief The tag lines directly above a line.
## @param lines The file's lines.
## @param at The line's index.
## @return Tag lines.
## @version 1
## @utility
def _tags_above(lines: list[str], at: int) -> list[str]:
    """@brief Tags. @return Lines."""
    out = []
    i = at - 1
    while i >= 0 and lines[i].strip().startswith("@"):
        out.insert(0, lines[i])
        i -= 1
    return out


## @brief How many lines the scenario at `at` spans.
## @param lines The file's lines.
## @param at The scenario's index.
## @return The count.
## @version 1
## @utility
def _scenario_end(lines: list[str], at: int) -> int:
    """THE NEXT SCENARIO, RULE OR FEATURE ends it — and the tag lines just above that block
    belong to it, not to this scenario.

    @brief Span.
    @return Count.
    """
    end = len(lines)
    for i in range(at + 1, len(lines)):
        match = _BLOCK.match(lines[i].strip())
        if match and match.group(1) not in ("Examples", "Scenarios"):
            end = i
            break
    while end > at + 1 and lines[end - 1].strip().startswith("@"):
        end -= 1
    return end - at


## @brief Gherkin lines as HTML.
## @param lines The lines.
## @return HTML.
## @version 1
## @utility
def _render(lines: list[str]) -> str:
    """@brief Render. @return HTML."""
    out, table, doc = [], [], None
    for raw in lines:
        line = raw.strip()
        if doc is not None:
            if line in ('"""', "```"):
                out.append(f'<pre class="docstring">{escape(chr(10).join(doc))}</pre>')
                doc = None
            else:
                doc.append(line)
            continue
        if line.startswith("|"):
            table.append([c.strip() for c in line.strip("|").split("|")])
            continue
        if table:
            out.append(_table(table))
            table = []
        if line in ('"""', "```"):
            doc = []
        elif line:
            out.append(_line(line))
    if table:
        out.append(_table(table))
    return "".join(out)


## @brief One Gherkin line: tags, a block heading, a step, or text.
## @param line The stripped line.
## @return HTML.
## @version 1
## @utility
def _line(line: str) -> str:
    """@brief Render a line. @return HTML."""
    if line.startswith("@"):
        chips = "".join(f'<span class="gtag">{escape(t)}</span>' for t in line.split())
        return f'<div class="gtags">{chips}</div>'
    match = _BLOCK.match(line)
    if match:
        kind = match.group(1).split()[0].lower()
        return (
            f'<div class="gblock g-{kind}"><span class="gk">{escape(match.group(1))}:</span>'
            f"{escape(match.group(2))}</div>"
        )
    word = line.split(" ", 1)[0]
    if word in _KEYWORDS:
        rest = line[len(word) :]
        return f'<div class="gstep"><span class="gk step">{escape(word)}</span>{escape(rest)}</div>'
    return f'<div class="gtext">{escape(line)}</div>'


## @brief An Examples or data table.
## @param rows Cell rows; the first is the header.
## @return HTML.
## @version 1
## @utility
def _table(rows: list[list[str]]) -> str:
    """@brief Table. @return HTML."""
    head = "".join(f"<th>{escape(c)}</th>" for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return f'<table class="gtable"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


## @brief Write a page per feature file, a section per scenario the site's tests name.
## @param repo_root The repository.
## @param scenarios Parsed scenarios (`imports.parse_features`).
## @param facts {test name: facts}.
## @param source The Sphinx source directory.
## @return {(scenario test id `file::name`, feature file): href} — keyed as the evidence names it.
## @version 1
## @req REQ-DDB-WIKI-026
def feature_pages(
    repo_root: Path, scenarios: list, facts: dict[str, TestFacts], source: Path
) -> dict[tuple[str, str], str]:
    """@brief Write feature pages. @return Hrefs."""
    from .symbols import anchor, page_for, symbol_href

    by_file: dict[str, list] = {}
    for sc in scenarios:
        by_file.setdefault(sc.file, []).append(sc)
    written: dict[tuple[str, str], str] = {}
    for rel, items in sorted(by_file.items()):
        try:
            text = (Path(repo_root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sections = []
        for sc in items:
            f = facts.get(sc.test_id, TestFacts())
            sections.append(
                f'<section class="symbol" id="{anchor(sc.name)}"><h2>{escape(sc.name)}</h2>'
                f"{verifies_block(f, {})}{render_scenario(text, sc.line)}</section>"
            )
            written[(sc.test_id, rel)] = symbol_href(sc.name, rel)
        page = [
            "---",
            "orphan: true",
            "---",
            "",
            f"# `{rel}`",
            "",
            "```{raw} html",
            *sections,
            "```",
            "",
        ]
        (Path(source) / f"{page_for(rel)}.md").write_text("\n".join(page), encoding="utf-8")
    return written


## @brief A test's result, the requirements it verifies (with the call path to an implementer
## when one is known) and its mutation outcomes.
## @param facts The test's facts.
## @param paths {requirement id: [function names from the test to an implementer]}.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-026
def verifies_block(facts: TestFacts, paths: dict[str, list[str]]) -> str:
    """@brief Verifies block. @return HTML."""
    from .htmltable import tag

    rows = "".join(
        f'<tr><td><a class="req-badge" href="requirements.html#{escape(r)}">{escape(r)}</a></td>'
        f'<td><span class="via via-{kind}">{kind}</span></td>'
        f"<td>{' → '.join(f'<code>{escape(n)}</code>' for n in paths.get(r, []))}</td></tr>"
        for r, kind in facts.verifies
    )
    out = f'<p class="result">Result: {tag(facts.status)}</p>'
    if rows:
        out += (
            '<h4>Verifies</h4><table class="verifies"><thead><tr><th>requirement</th><th>linked'
            f"</th><th>path to the implementer</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    if facts.mutations:
        out += (
            '<h4>Mutations</h4><ul class="modal-list">'
            + "".join(f"<li><code>{escape(m)}</code> {escape(o)}</li>" for m, o in facts.mutations)
            + "</ul>"
        )
    return out
