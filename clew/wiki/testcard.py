# SPDX-License-Identifier: MIT
"""The test card: WHY a test exists and WHAT it checks, at the top of its page (owner review 3).

OWNER REVIEW 2026-11-22: "its not showing WHAT the test is checking, what its asserted, WHY does the
test exist? what EXACTLY in a visual sense is the test there for". Owner Q/A the same day:

- WHY is the test's own words — its docstring's first paragraph (the index's brief when there is no
  Python docstring to read) — and the requirements it is DECLARED for (`tag`, `catalog`). What it
  merely reaches by coverage (`measured`, `inferred`) is folded on the page, not claimed here.
- Given / When / Then is the test's STRUCTURE, read from its syntax, never invented prose: Given is
  the setup before its first call into product code, When is the statements that call product
  code, Then is each assertion in readable form ("panel contains …"), marked with the run's result.
- Python is read with `ast`. A test in another language keeps WHY and its checks section below.

The playable flowchart and declared failure modes are 2.1 (owner ruling).

@brief Render a test's WHY / Given / When / Then card.
@version 1
"""

from __future__ import annotations

import ast
import textwrap
from html import escape
from typing import Any

## How many statements a card panel shows before folding the rest.
_SHOWN = 3
## Requirement links that state intent, as opposed to coverage reach.
DECLARED_LINKS = ("tag", "catalog")
## A comparison operator as the words a check reads with.
_OPS = {
    ast.Eq: "equals",
    ast.NotEq: "differs from",
    ast.Lt: "is less than",
    ast.LtE: "is at most",
    ast.Gt: "is greater than",
    ast.GtE: "is at least",
    ast.Is: "is",
    ast.IsNot: "is not",
}


## @brief The card: WHY, then Given / When / Then, for one test definition.
## @param lines The test's lines, from its `def` line.
## @param d The definition (name, file).
## @param product Names of the product functions the test calls.
## @param facts The test's facts (status, verifies).
## @param brief The index's brief, used when there is no Python docstring.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-026
def test_card(lines: list[str], d: Any, product: set[str], facts: Any, brief: str = "") -> str:
    """ABSENT, NOT INVENTED: a part the test does not have is not drawn.

    @brief Test card.
    @return HTML.
    """
    src = textwrap.dedent("\n".join(lines))
    fn = _parse(src, d.name) if d.file.endswith(".py") else None
    why = (_docstring_why(fn) if fn else "") or brief
    reqs = [r for r, kind in getattr(facts, "verifies", ()) if kind in DECLARED_LINKS]
    status = getattr(facts, "status", "absent") or "absent"
    parts = [_why_html(why, reqs)]
    if fn is not None:
        parts.append(_phases_html(_phases(fn, product, src), status))
    return (
        '<section class="test-card"><h2>What this test is for</h2>' + "".join(parts) + "</section>"
    )


## @brief The test's own function node, parsed from its lines.
## @param src The test's source, dedented, from its `def`.
## @param name The test's name.
## @return The node, or None when it does not parse.
## @version 1
## @utility
def _parse(src: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """@brief Parse the test. @return Node or None."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    return next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
        ),
        None,
    )


## @brief The docstring's first paragraph, without doxygen tag lines.
## @param fn The test's node.
## @return Text, or "".
## @version 1
## @utility
def _docstring_why(fn: ast.AST) -> str:
    """@brief First paragraph. @return Text."""
    doc = ast.get_docstring(fn) or ""
    first = doc.split("\n\n", 1)[0]
    kept = [ln for ln in first.splitlines() if not ln.strip().startswith("@")]
    return " ".join(" ".join(kept).split())


## @brief Split a test body into Given, When and Then.
## @param fn The test's node.
## @param product Names of product functions.
## @param src The source the node was parsed from (statements are shown AS WRITTEN).
## @return (given statements, when statements, then checks), as text.
## @version 1
## @utility
def _phases(fn: Any, product: set[str], src: str) -> tuple[list[str], list[str], list[str]]:
    """GIVEN ENDS AT THE FIRST PRODUCT CALL; every later non-assertion statement that calls product
    code is When; each assertion is one or more Then checks (`a and b` reads as two).

    @brief Phases.
    @return Triple.
    """
    body = [
        s
        for s in fn.body
        if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))
    ]
    given: list[str] = []
    when: list[str] = []
    then: list[str] = []

    def text(node: ast.AST) -> str:
        return " ".join((ast.get_source_segment(src, node) or ast.unparse(node)).split())

    for stmt in body:
        if isinstance(stmt, ast.Assert):
            then.extend(_checks(stmt.test, text))
            ## Owner review 3: a product call made INSIDE the assertion is the When.
            when.extend(text(c) for c in _product_calls(stmt.test, product) if text(c) not in when)
        elif _raises(stmt):
            then.append(f"raises {text(stmt.items[0].context_expr.args[0])}")
            when.extend(text(s) for s in stmt.body)
        elif when or _calls_product(stmt, product):
            when.append(text(stmt))
        elif not isinstance(stmt, (ast.Import, ast.ImportFrom)):
            ## Owner review 3: an import is not setup.
            given.append(text(stmt))
    return given, when, then


## @brief The product calls inside an expression, outermost first.
## @param node The expression.
## @param product Names of product functions.
## @return Call nodes.
## @version 1
## @utility
def _product_calls(node: ast.AST, product: set[str]) -> list[ast.Call]:
    """@brief Product calls. @return Calls."""
    return [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) in product
    ]


## @brief Whether a statement is `with pytest.raises(X): …`.
## @param stmt The statement.
## @return True or False.
## @version 1
## @utility
def _raises(stmt: ast.AST) -> bool:
    """@brief raises block. @return Flag."""
    if not isinstance(stmt, ast.With) or not stmt.items:
        return False
    call = stmt.items[0].context_expr
    return (
        isinstance(call, ast.Call)
        and getattr(call.func, "attr", "") == "raises"
        and bool(call.args)
    )


## @brief Whether a statement calls a product function.
## @param stmt The statement.
## @param product Names of product functions.
## @return True or False.
## @version 1
## @utility
def _calls_product(stmt: ast.AST, product: set[str]) -> bool:
    """@brief Product call. @return Flag."""
    for node in ast.walk(stmt):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in product:
                return True
    return False


## @brief An assertion's checks in readable form; `a and b` is two checks.
## @param expr The asserted expression.
## @param text Source text of a node, as written.
## @return Checks.
## @version 1
## @utility
def _checks(expr: ast.AST, text: Any) -> list[str]:
    """@brief Readable checks. @return List."""
    if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.And):
        return [c for value in expr.values for c in _checks(value, text)]
    return [_readable(expr, text)]


## @brief One check in words: "x contains y", "a equals b", "x is false".
## @param expr The expression.
## @param text Source text of a node, as written.
## @return Text.
## @version 1
## @utility
def _readable(expr: ast.AST, text: Any) -> str:
    """THE CODE'S OWN TERMS, re-ordered to read as a sentence; anything unusual stays as written.

    @brief Read one check.
    @return Text.
    """
    if isinstance(expr, ast.Compare) and len(expr.ops) == 1:
        left, op, right = text(expr.left), expr.ops[0], text(expr.comparators[0])
        if isinstance(op, (ast.In, ast.NotIn)):
            verb = "contains" if isinstance(op, ast.In) else "does not contain"
            return f"{right} {verb} {left}"
        if type(op) in _OPS:
            return f"{left} {_OPS[type(op)]} {right}"
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return f"{text(expr.operand)} is false"
    return f"{text(expr)} holds"


## @brief The WHY panel.
## @param why The test's own words.
## @param reqs Requirements it is declared for.
## @return HTML.
## @version 1
## @utility
def _why_html(why: str, reqs: list[str]) -> str:
    """@brief WHY. @return HTML."""
    text = (
        f"<p>{escape(why)}</p>" if why else '<p class="none">The test says nothing about why.</p>'
    )
    badges = " ".join(
        f'<a class="req-badge" href="req-{escape(r)}.html">{escape(r)}</a>' for r in reqs
    )
    verifies = f'<p class="tc-reqs">Verifies {badges}</p>' if badges else ""
    return f'<div class="tc-why"><p class="tc-h">Why it exists</p>{text}{verifies}</div>'


## @brief The Given → When → Then strip.
## @param phases (given, when, then).
## @param status The run's result for the test.
## @return HTML.
## @version 1
## @utility
def _phases_html(phases: tuple[list[str], list[str], list[str]], status: str) -> str:
    """VISUAL: three panels in reading order with arrows between; each check marked with the run.

    @brief Phases strip.
    @return HTML.
    """
    given, when, then = phases

    def panel(cls: str, head: str, rows: list[str], code: bool = True, fold: bool = True) -> str:
        items = [f"<li><code>{escape(r)}</code></li>" if code else r for r in rows]
        empty = '<li class="none">—</li>'
        ## A LONG PANEL FOLDS: three statements shown, the rest one click away (owner review 3).
        if fold and len(items) > _SHOWN + 2:
            rest = "".join(items[_SHOWN:])
            more = f'<details class="tc-more"><summary>{len(items) - _SHOWN} more</summary><ol start="{_SHOWN + 1}">{rest}</ol></details>'
            return f'<div class="{cls}"><p class="tc-h">{head}</p><ol>{"".join(items[:_SHOWN])}</ol>{more}</div>'
        return (
            f'<div class="{cls}"><p class="tc-h">{head}</p><ol>{"".join(items) or empty}</ol></div>'
        )

    mark = {"passed": "✓", "failed": "✗", "error": "✗"}.get(status, "·")
    checks = [
        f'<li class="ck {escape(status)}"><span class="mk">{mark}</span> {escape(c)}</li>'
        for c in then
    ]
    ## A Given with nothing in it is not drawn (owner review 3).
    first = panel("tc-given", "Given", given) + '<span class="tc-arrow">→</span>' if given else ""
    return (
        f'<div class="tc-strip{"" if given else " no-given"}">'
        + first
        + panel("tc-when", "When", when)
        + '<span class="tc-arrow">→</span>'
        ## THEN NEVER FOLDS: the checks are what the card is for.
        + panel("tc-then", "Then", checks, code=False, fold=False)
        + "</div>"
    )
