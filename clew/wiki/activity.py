# SPDX-License-Identifier: MIT
"""A function's activity diagram: its control flow, drawn from its parsed body (round 5, P5.5).

OWNER (round 5): diagrams at two zoom levels — a test's call-flow boxes, and clicking a box opens
that function's ACTIVITY DIAGRAM with the lines the test executed lit. Owner Q/A 2026-11-20: one
diagram PER FUNCTION, on its own page, lit by the link (`?lit=12-15,20`), so the site's weight grows
with its functions, not with tests × functions.

THE STEPS COME FROM A PARSER. Python through `ast`, C and C++ through tree-sitter. Each step is one
statement, condition, loop, branch label or exit, with its absolute line range in `data-l`, which is
what `clew.js` lights from the link:

| step | drawn as |
|---|---|
| statement | a box |
| condition (`if`) | a diamond; its branch is indented below it, `else` labelled |
| loop (`for`, `while`, `do`) | a diamond with a back edge from its body's last step |
| exit (`return`, `raise`, `throw`) | a rounded terminal |

Static SVG: no script to draw, so it shows (unlit) without JavaScript and prints as shown. Statement
text is the full statement, whitespace collapsed — never cut.

@brief Activity diagrams for functions, from their parsed bodies.
@version 1
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import PurePosixPath

STMT, COND, LOOP, ELSE, EXIT = "stmt", "cond", "loop", "else", "exit"
_PITCH, _INDENT, _CHAR, _PAD, _H = 30, 28, 6.9, 10, 22
_C = {".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp"}


## @brief One step of a function's control flow.
## @version 1
@dataclass(frozen=True)
class Step:
    """@brief Kind, text, absolute first and last line, nesting depth, and (for a loop) its end."""

    kind: str
    text: str
    first: int
    last: int
    depth: int


## @brief A function's steps, from its source lines.
## @param lines The definition's lines (the signature line first).
## @param rel Its file, whose suffix picks the parser.
## @param first_line The file line of `lines[0]`.
## @return Steps in source order; [] for a language without a parser or a body that will not parse.
## @version 1
## @req REQ-DDB-WIKI-045
def steps_of(lines: list[str], rel: str, first_line: int) -> list[Step]:
    """@brief Dispatch by language. @return Steps."""
    suffix = PurePosixPath(rel).suffix
    if suffix == ".py":
        return _py_steps(lines, first_line)
    return _c_steps(lines, _C[suffix], first_line) if suffix in _C else []


## @brief The SVG for a function's steps.
## @param steps Its steps.
## @param label The function's name, for the accessible label.
## @return SVG HTML, or "" when there are no steps.
## @version 1
## @req REQ-DDB-WIKI-045
def activity_svg(steps: list[Step], label: str) -> str:
    """@brief Rows top to bottom, indented by depth, loop back edges on the right. @return SVG."""
    if not steps:
        return ""
    width = max(s.depth * _INDENT + len(s.text) * _CHAR + 3 * _PAD for s in steps) + 40
    height = _PITCH * len(steps) + _PAD
    parts = [_edge(steps, i) for i in range(len(steps) - 1)]
    parts += [_back_edge(steps, i, width) for i, s in enumerate(steps) if s.kind == LOOP]
    parts += [_node(s, i) for i, s in enumerate(steps)]
    return (
        f'<svg class="activity" role="img" aria-label="activity of {escape(label)}: '
        f'{len(steps)} steps" viewBox="0 0 {width:.0f} {height}" width="{width:.0f}" '
        f'height="{height}">' + "".join(parts) + "</svg>"
    )


## @brief One step's shape and text.
## @param step The step.
## @param i Its row.
## @return SVG.
## @version 1
## @utility
def _node(step: Step, i: int) -> str:
    """@brief Box, diamond-ended box, label, or terminal. @return SVG."""
    x, y = step.depth * _INDENT + _PAD, i * _PITCH + 4
    w = len(step.text) * _CHAR + 2 * _PAD
    radius = {EXIT: 11, ELSE: 0}.get(step.kind, 3)
    marker = "◇ " if step.kind in (COND, LOOP) else ""
    title = f"<title>lines {step.first}–{step.last}</title>"
    return (
        f'<g class="step s-{step.kind}" data-l="{step.first}-{step.last}">{title}'
        f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{_H}" rx="{radius}"/>'
        f'<text x="{x + _PAD}" y="{y + 15}">{marker}{escape(step.text)}</text></g>'
    )


## @brief The connector from one step to the next.
## @param steps All steps.
## @param i The upper step's row.
## @return SVG.
## @version 1
## @utility
def _edge(steps: list[Step], i: int) -> str:
    """@brief A vertical, then horizontal, line between consecutive rows. @return SVG."""
    a, b = steps[i], steps[i + 1]
    x1, x2 = a.depth * _INDENT + _PAD + 6, b.depth * _INDENT + _PAD + 6
    y1, y2 = i * _PITCH + 4 + _H, (i + 1) * _PITCH + 4
    return f'<path class="flow" d="M{x1} {y1} V{y2 - 4} H{x2} V{y2}"/>'


## @brief A loop's back edge, from its body's last step to the loop.
## @param steps All steps.
## @param i The loop's row.
## @param width The diagram's width.
## @return SVG.
## @version 1
## @utility
def _back_edge(steps: list[Step], i: int, width: float) -> str:
    """@brief Right-hand return path. @return SVG."""
    depth = steps[i].depth
    j = i
    while j + 1 < len(steps) and steps[j + 1].depth > depth:
        j += 1
    x = width - 20 - depth * 6
    y1, y2 = j * _PITCH + 15, i * _PITCH + 15
    return f'<path class="loop-back" d="M{x - 14} {y1} H{x} V{y2} H{x - 14}"/>'


## @brief Python steps through `ast`.
## @param lines The definition's lines.
## @param first_line The file line of `lines[0]`.
## @return Steps.
## @version 1
## @utility
def _py_steps(lines: list[str], first_line: int) -> list[Step]:
    """@brief Parse, then walk the function's body. @return Steps."""
    source = textwrap.dedent("\n".join(lines))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    func = next(
        (n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None
    )
    out: list[Step] = []
    if func is not None:
        _py_block(_without_docstring(func.body), 0, source, first_line, out)
    return out


## @brief A body without its leading docstring.
## @param body Statements.
## @return Statements.
## @version 1
## @utility
def _without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """@brief Drop a leading string expression. @return Body."""
    first = body[0] if body else None
    is_doc = isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant)
    return body[1:] if is_doc and isinstance(first.value.value, str) else body


## @brief Emit the steps of one Python block.
## @param body Statements.
## @param depth Nesting depth.
## @param source The dedented source.
## @param base The file line of the source's first line.
## @param out Collects steps.
## @return None.
## @version 1
## @utility
def _py_block(body: list[ast.stmt], depth: int, source: str, base: int, out: list[Step]) -> None:
    """@brief Recurse into compound statements. @return None."""
    for node in body:
        first, last = base + node.lineno - 1, base + (node.end_lineno or node.lineno) - 1
        header = _py_header(node, source)
        if isinstance(node, ast.If):
            out.append(Step(COND, header, first, base + node.test.end_lineno - 1, depth))
            _py_block(node.body, depth + 1, source, base, out)
            _py_orelse(node, depth, source, base, out)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            out.append(Step(LOOP, header, first, first, depth))
            _py_block(node.body, depth + 1, source, base, out)
        elif isinstance(node, (ast.With, ast.AsyncWith, ast.Try)):
            out.append(Step(STMT, header, first, first, depth))
            _py_block(node.body, depth + 1, source, base, out)
            for handler in getattr(node, "handlers", ()):
                h = base + handler.lineno - 1
                out.append(Step(ELSE, _py_header(handler, source), h, h, depth))
                _py_block(handler.body, depth + 1, source, base, out)
        else:
            kind = EXIT if isinstance(node, (ast.Return, ast.Raise)) else STMT
            out.append(Step(kind, header, first, last, depth))


## @brief An `if`'s alternative: an `elif` as a condition at the same depth, else a labelled branch.
## @param node The `if`.
## @param depth Its depth.
## @param source The dedented source.
## @param base The file line of the source's first line.
## @param out Collects steps.
## @return None.
## @version 1
## @utility
def _py_orelse(node: ast.If, depth: int, source: str, base: int, out: list[Step]) -> None:
    """`ast` RECORDS NO LINE FOR `else:` itself, only for the statement after it, so the keyword's
    line is found by scanning upward from there. An `elif` is an `If` alone in `orelse` whose line
    starts with `elif`: it is drawn as a condition at the same depth, not as `else` then `if`.

    @brief Alternative branch.
    @return None.
    """
    if not node.orelse:
        return
    lines = source.splitlines()
    head = node.orelse[0]
    if len(node.orelse) == 1 and isinstance(head, ast.If):
        if lines[head.lineno - 1].lstrip().startswith("elif"):
            text = "elif " + " ".join((ast.get_source_segment(source, head.test) or "").split())
            out.append(
                Step(COND, text, base + head.lineno - 1, base + head.test.end_lineno - 1, depth)
            )
            _py_block(head.body, depth + 1, source, base, out)
            _py_orelse(head, depth, source, base, out)
            return
    row = head.lineno - 1
    while row > node.body[-1].end_lineno - 1 and not lines[row].lstrip().startswith("else"):
        row -= 1
    out.append(Step(ELSE, "else", base + row, base + row, depth))
    _py_block(node.orelse, depth + 1, source, base, out)


## @brief The text a step shows: the statement, or a compound statement's header line.
## @param node The statement.
## @param source The dedented source.
## @return Text, whitespace collapsed.
## @version 1
## @utility
def _py_header(node: ast.AST, source: str) -> str:
    """@brief Header of a compound statement, else the whole statement. @return Text."""
    text = ast.get_source_segment(source, node) or ""
    compound = isinstance(
        node,
        (
            ast.If,
            ast.For,
            ast.AsyncFor,
            ast.While,
            ast.With,
            ast.AsyncWith,
            ast.Try,
            ast.ExceptHandler,
        ),
    )
    if compound:
        text = text.split("\n", 1)[0].rstrip(":").rstrip()
    return " ".join(text.split())


## @brief C and C++ steps through tree-sitter.
## @param lines The definition's lines.
## @param lang `c` or `cpp`.
## @param first_line The file line of `lines[0]`.
## @return Steps.
## @version 1
## @utility
def _c_steps(lines: list[str], lang: str, first_line: int) -> list[Step]:
    """@brief Find the function's body, then walk it. @return Steps."""
    from ..tsnode import Parser

    root = Parser(lang).parse("\n".join(lines).encode()).root_node
    body = _first(root, "compound_statement")
    out: list[Step] = []
    if body is not None:
        _c_block(body, 0, first_line, out)
    return out


## @brief The first descendant of a type.
## @param node A tree-sitter node.
## @param kind The node type.
## @return The node, or None.
## @version 1
## @utility
def _first(node, kind: str):  # noqa: ANN001, ANN201
    """@brief Breadth-first search. @return Node or None."""
    queue = [node]
    while queue:
        current = queue.pop(0)
        if current.type == kind:
            return current
        queue.extend(current.children)
    return None


## @brief Emit the steps of one C/C++ block or statement.
## @param node A compound statement or single statement.
## @param depth Nesting depth.
## @param base The file line of the parsed text's first line.
## @param out Collects steps.
## @return None.
## @version 1
## @utility
def _c_block(node, depth: int, base: int, out: list[Step]) -> None:  # noqa: ANN001
    """@brief Recurse into if / loops / blocks. @return None."""
    children = node.named_children if node.type == "compound_statement" else [node]
    for child in children:
        if child.type == "comment":
            continue
        first, last = base + child.start_point[0], base + child.end_point[0]
        if child.type == "if_statement":
            cond = child.child_by_field_name("condition")
            out.append(Step(COND, f"if {_collapse(cond)}", first, base + cond.end_point[0], depth))
            _c_block(child.child_by_field_name("consequence"), depth + 1, base, out)
            alt = child.child_by_field_name("alternative")
            if alt is not None:
                inner = (
                    alt.named_children[0]
                    if alt.type == "else_clause" and alt.named_children
                    else alt
                )
                out.append(
                    Step(ELSE, "else", base + alt.start_point[0], base + alt.start_point[0], depth)
                )
                _c_block(inner, depth + 1, base, out)
        elif child.type in ("for_statement", "while_statement", "do_statement", "for_range_loop"):
            head = _collapse(child).split("{", 1)[0].strip()
            out.append(Step(LOOP, head, first, first, depth))
            loop_body = child.child_by_field_name("body")
            if loop_body is not None:
                _c_block(loop_body, depth + 1, base, out)
        elif child.type == "compound_statement":
            _c_block(child, depth, base, out)
        else:
            kind = EXIT if child.type in ("return_statement", "throw_statement") else STMT
            out.append(Step(kind, _collapse(child), first, last, depth))


## @brief A node's text with whitespace collapsed.
## @param node A tree-sitter node.
## @return Text.
## @version 1
## @utility
def _collapse(node) -> str:  # noqa: ANN001
    """@brief Decode and collapse. @return Text."""
    raw = node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""
    return " ".join(raw.split())
